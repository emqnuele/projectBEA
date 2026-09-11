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
import { VRMAnimationLoaderPlugin, createVRMAnimationClip } from '@pixiv/three-vrm-animation';

import { createLife } from './life.js';

const EMOTIONS = ['happy', 'angry', 'sad', 'relaxed', 'surprised', 'neutral'];

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
    scene.add(vrm.scene);

    const mixer = new THREE.AnimationMixer(vrm.scene);
    const clips = new Map();
    let current = null;
    let playGeneration = 0;

    mixer.addEventListener('finished', (event) => {
        // the body is handed back the moment the gesture ends; the clip fades
        // out under the idle motion easing in over it, so neither one snaps
        event.action.fadeOut(0.3);
        if (current === event.action) current = null;
    });

    frame(config.shot || 'bust');
    const life = createLife(vrm, camera, scene);

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

    async function play(name) {
        if (!name) return;
        // two behaviours asked for fifty milliseconds apart race through the
        // loader; the one that finishes second is the newer one, but the one
        // that *started* second is what belongs on stage
        const generation = ++playGeneration;
        try {
            if (!clips.has(name)) {
                const loaded = await loader.loadAsync(`/stage/clips/${encodeURIComponent(name)}`);
                const [animation] = loaded.userData.vrmAnimations || [];
                if (!animation) throw new Error('no animation inside it');
                clips.set(name, createVRMAnimationClip(animation, vrm));
            }
            // a newer request won the race while this one was loading: cached
            // for next time, but not played on top of it
            if (generation !== playGeneration) return;
            const action = mixer.clipAction(clips.get(name));
            // a behaviour is a gesture, not a loop. Left on the default the
            // first shrug of the stream repeats until the page is reloaded —
            // and the body never goes back to breathing on its own.
            action.setLoop(THREE.LoopOnce, 1);
            action.clampWhenFinished = true;
            current?.fadeOut(0.25);
            action.reset().fadeIn(0.25).play();
            current = action;
        } catch (error) {
            console.warn(`[stage] behaviour "${name}" did not play:`, error.message);
        }
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
        for (const name of EMOTIONS) {
            const now = manager.getValue(name) ?? 0;
            manager.setValue(name, THREE.MathUtils.lerp(now, target[name] ?? 0, k));
        }

        let frame = null;
        if (speaking && mouth.frames.length) {
            const index = Math.floor((performance.now() - mouth.startedAt) / 1000 * mouth.fps);
            frame = index < mouth.frames.length ? mouth.frames[index] : null;
        }

        const m = 1 - Math.exp(-MOUTH_EASING * delta);
        jaw.open = THREE.MathUtils.lerp(jaw.open, frame ? frame[0] : 0, m);
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
    const clock = new THREE.Clock();
    let owed = 0;

    renderer.setAnimationLoop(() => {
        const delta = clock.getDelta();
        owed += delta;
        if (owed < minFrame) return;
        const step = owed;
        owed = 0;

        mixer.update(step);
        life.update(step, Boolean(current?.isRunning()));
        drive(step);
        vrm.update(step);
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
            }

            if (!animate) {
                // snap rather than ease, so a reconnect is invisible on stream
                const manager = vrm.expressionManager;
                for (const name of EMOTIONS) manager?.setValue(name, target[name] ?? 0);
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
            if (patch.perform) play(patch.perform);
        },

        /** Settings changed under a running page: shot and background apply live. */
        setLook(next = {}) {
            setBackground(renderer, next.background);
            frame(next.shot || 'bust');
        },
    };
}
