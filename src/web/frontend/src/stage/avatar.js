/**
 * The 3D body: a VRM, rendered transparent for an OBS browser source.
 *
 * The engine sends expression weights and what her mouth does; nothing here
 * knows what a mood is. Everything she does when the engine is *not* sending
 * anything — blinking, breathing, looking around — lives in `life.js`.
 *
 * Three things that look like details and are not:
 *
 *  - The 180° turn belongs to VRM 0.x only. `VRMUtils.rotateVRM0` applies it
 *    where it is due; an unconditional `rotation.y = Math.PI` shows the back of
 *    every VRM 1.0 model.
 *  - The camera is framed off the `head` bone, never off numbers. That is what
 *    makes the same code frame a 1.4 m model and a 1.8 m one the same way.
 *  - This page runs inside OBS for hours at a time, so the loop does the least
 *    it can get away with and the frame rate can be capped from config.
 */

import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';
import { VRMAnimationLoaderPlugin, VRMLookAtQuaternionProxy } from '@pixiv/three-vrm-animation';

import { createBody } from './body.js';
import { EMOTIONS, faceTargets, mouthScale, resolveExpression } from './face.js';
import { createLife } from './life.js';

// The mouth shapes, dark to bright. This order is a contract with
// `src/core/expression/face.py`, which places every frame of a line on the same
// axis as one number — reorder one without the other and she says the wrong
// vowels perfectly in time.
const VISEMES = ['ou', 'oh', 'aa', 'ee', 'ih'];

// how fast a face settles into a new mood. Slow enough to read as a change of
// expression, fast enough that the line she is saying still matches it.
const EASING = 8;

// the mouth, which has to keep up with speech rather than read as a change of
// mind. Fast enough to hit every frame the engine sent, slow enough that the
// steps between them are not visible.
const MOUTH_EASING = 22;

// the bust shot, as a height in metres to fit in frame. The other two are
// measured off the model's own bones rather than fixed here.
const BUST_SPAN = 0.52;

function setBackground(renderer, colour) {
    if (colour) renderer.setClearColor(new THREE.Color(colour), 1);
    else renderer.setClearColor(0x000000, 0);
}

export async function createAvatar(root, config = {}) {
    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(window.innerWidth, window.innerHeight);
    // transparent unless a colour was asked for: OBS composites the page over
    // the scene, so anything painted here that is not her is on the stream
    setBackground(renderer, config.background);
    root.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(30, window.innerWidth / window.innerHeight, 0.1, 20);

    const key = new THREE.DirectionalLight(0xffffff, 2.0);
    key.position.set(1, 2, 1.5);          // from the camera side, or the face goes dark
    scene.add(key, new THREE.AmbientLight(0xffffff, 1.1));

    const loader = new GLTFLoader();
    loader.register((parser) => new VRMLoaderPlugin(parser));
    loader.register((parser) => new VRMAnimationLoaderPlugin(parser));

    const gltf = await loader.loadAsync('/stage/model');
    const vrm = gltf.userData.vrm;
    if (!vrm) throw new Error('that file loaded, but it is not a VRM');

    VRMUtils.combineSkeletons(gltf.scene);
    VRMUtils.rotateVRM0(vrm);             // only 0.x needs turning; 1.0 already faces us
    // skinned bounds do not follow the bones, so an arm raised past them would be culled
    vrm.scene.traverse((object) => { object.frustumCulled = false; });
    if (vrm.lookAt) {
        // clips that drive the gaze need it, and without one each clip built creates its own
        const proxy = new VRMLookAtQuaternionProxy(vrm.lookAt);
        proxy.name = 'VRMLookAtQuaternionProxy';
        vrm.scene.add(proxy);
    }
    scene.add(vrm.scene);

    frame(config.shot || 'bust');

    const loadAnimation = async (name) => {
        const loaded = await loader.loadAsync(`/stage/clips/${encodeURIComponent(name)}`);
        const [animation] = loaded.userData.vrmAnimations || [];
        if (!animation) throw new Error('no animation inside it');
        return animation;
    };
    const body = createBody(vrm, loadAnimation, config);
    const life = createLife(vrm, camera, scene);

    // the model's own names for the emotions: a vrm 0.x keeps surprised as a custom "Surprised"
    const available = (vrm.expressionManager?.expressions || []).map((e) => e.expressionName);
    const names = {};
    for (const name of EMOTIONS) {
        const found = resolveExpression(available, name);
        if (found) names[name] = found;
    }
    // what the file declared, so turning the setting off puts it back
    const declaredBlink = new Map();
    for (const name of EMOTIONS) {
        const expression = names[name] && vrm.expressionManager?.getExpression(names[name]);
        if (expression && name !== 'neutral') declaredBlink.set(expression, expression.overrideBlink);
    }
    let face = {};
    function setFace(next) {
        face = {
            intensity: Number(next.expression_intensity ?? 1),
            underEmotion: Number(next.mouth_under_emotion ?? 1),
        };
        // 'none' adds a blink on top of a face whose eyes are already shut in a smile
        const blend = next.face_blend_blink !== false;
        for (const [expression, declared] of declaredBlink) {
            expression.overrideBlink = blend && declared === 'none' ? 'blend' : declared;
        }
    }
    setFace(config);

    function frame(shot) {
        const bone = (name) => vrm.humanoid?.getNormalizedBoneNode(name)
            || vrm.humanoid?.getRawBoneNode(name);
        const head = bone('head');
        const hips = bone('hips');
        if (!head || !hips) {
            camera.position.set(0, 1.3, 1.6);
            camera.lookAt(0, 1.3, 0);
            return;
        }

        vrm.scene.updateWorldMatrix(true, true);
        const headY = head.getWorldPosition(new THREE.Vector3()).y;
        const hipsY = hips.getWorldPosition(new THREE.Vector3()).y;

        let centre;
        let span;
        if (shot === 'full') {
            const box = new THREE.Box3().setFromObject(vrm.scene);
            centre = (box.max.y + box.min.y) / 2;
            span = (box.max.y - box.min.y) * 1.08;
        } else if (shot === 'half') {
            centre = (headY + hipsY) / 2;
            span = (headY - hipsY) * 1.5;
        } else {
            centre = headY - 0.06;        // a little headroom, the way a shot is framed
            span = BUST_SPAN;
        }

        const distance = span / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2));
        camera.position.set(0, centre, distance);
        camera.lookAt(0, centre, 0);
    }

    // what the engine last said she is
    const target = Object.fromEntries(EMOTIONS.map((name) => [name, 0]));
    target.neutral = 1;
    let mouth = { frames: [], fps: 30, startedAt: 0 };
    let speaking = false;

    // where the mouth is right now, as opposed to where the line says it should
    // be: eased, so 30 frames a second do not arrive as 30 steps
    const jaw = { open: 0, shape: 0.5 };

    function drive(delta) {
        const manager = vrm.expressionManager;
        if (!manager) return;

        const k = 1 - Math.exp(-EASING * delta);
        const goal = faceTargets(target, face.intensity);
        const worn = {};
        for (const name of EMOTIONS) {
            const actual = names[name];
            if (!actual) continue;
            worn[name] = THREE.MathUtils.lerp(manager.getValue(actual) ?? 0, goal[name], k);
            manager.setValue(actual, worn[name]);
        }

        let frame = null;
        if (speaking && mouth.frames.length) {
            const index = Math.floor((performance.now() - mouth.startedAt) / 1000 * mouth.fps);
            frame = index < mouth.frames.length ? mouth.frames[index] : null;
        }

        const m = 1 - Math.exp(-MOUTH_EASING * delta);
        const wanted = frame ? frame[0] * mouthScale(worn, face.underEmotion) : 0;
        jaw.open = THREE.MathUtils.lerp(jaw.open, wanted, m);
        // the shape is only chased while there is something to say: easing it
        // back to the middle between two words makes the mouth chew
        if (frame) jaw.shape = THREE.MathUtils.lerp(jaw.shape, frame[1], m);
        shapeMouth(manager, jaw.open, jaw.shape);
    }

    /** One number on the vowel axis, as a blend of the two shapes it falls between. */
    function shapeMouth(manager, open, shape) {
        const position = THREE.MathUtils.clamp(shape, 0, 1) * (VISEMES.length - 1);
        const lower = Math.min(Math.floor(position), VISEMES.length - 2);
        const across = position - lower;

        for (let i = 0; i < VISEMES.length; i += 1) {
            let weight = 0;
            if (i === lower) weight = open * (1 - across);
            else if (i === lower + 1) weight = open * across;
            manager.setValue(VISEMES[i], weight);
        }
    }

    function silence(manager) {
        jaw.open = 0;
        for (const name of VISEMES) manager?.setValue(name, 0);
    }

    // a browser source has a whole stream to share a machine with, and nothing
    // here is worth more than the encoder. 0 means "as fast as the display".
    const minFrame = config.max_fps > 0 ? 1 / config.max_fps : 0;
    // spring bones scale with the step, so a page stalled for seconds would throw the hair in one frame
    const maxStep = Math.max(1 / 20, minFrame);
    const clock = new THREE.Clock();
    let owed = 0;

    renderer.setAnimationLoop(() => {
        const delta = clock.getDelta();
        owed += delta;
        if (owed < minFrame) return;
        const step = owed;
        owed = 0;
        const dt = Math.min(step, maxStep);

        life.undo();
        body.update(step);
        life.update(dt, { busy: body.busy(), loudness: jaw.open, gazeClip: body.gazeShare() });
        drive(dt);
        vrm.update(dt);
        renderer.render(scene, camera);
    });

    const onResize = () => {
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
    };
    window.addEventListener('resize', onResize);

    return {
        /**
         * @param patch what changed
         * @param animate false when this is the state on connect: a page that
         *        reloads mid-sentence must not replay the behaviour or the mouth
         */
        apply(patch, { animate = true } = {}) {
            if (patch.expressions) Object.assign(target, patch.expressions);
            if ('state' in patch) {
                speaking = patch.state === 'talking';
                life.setState(patch.state);
                body.setState(patch.state);
            }

            if (!animate) {
                // snap rather than ease, so a reconnect is invisible on stream
                const manager = vrm.expressionManager;
                const goal = faceTargets(target, face.intensity);
                for (const name of EMOTIONS) if (names[name]) manager?.setValue(names[name], goal[name]);
                mouth = { frames: [], fps: 30, startedAt: 0 };
                silence(manager);
                life.settle();
                return;
            }

            if (patch.envelope) {
                mouth = {
                    frames: patch.envelope,
                    fps: patch.envelope_fps || 30,
                    startedAt: performance.now(),
                };
            }
            if (patch.perform) body.play(patch.perform);
        },

        /** Settings changed under a running page: shot and background apply live. */
        setLook(next = {}) {
            setBackground(renderer, next.background);
            frame(next.shot || 'bust');
            body.setConfig(next);
            setFace(next);
        },
    };
}
