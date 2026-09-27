// headless pose probe: loads a vrm and .vrma clips in node and measures where the arms point
import { readFileSync } from 'node:fs';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';
import { VRMAnimationLoaderPlugin, createVRMAnimationClip } from '@pixiv/three-vrm-animation';

// node has no <img>: textures resolve to an empty image, geometry and bones are untouched
globalThis.self = globalThis;
globalThis.document = {
  createElementNS: () => {
    const listeners = {};
    return {
      style: {}, width: 1, height: 1,
      addEventListener: (t, f) => { listeners[t] = f; },
      removeEventListener: () => {},
      set src(_v) { setTimeout(() => listeners.load?.({}), 0); },
    };
  },
};

const loader = new GLTFLoader();
loader.register((p) => new VRMLoaderPlugin(p));
loader.register((p) => new VRMAnimationLoaderPlugin(p));
export const parse = (path) => new Promise((ok, ko) => {
  const b = readFileSync(path);
  loader.parse(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength), '', ok, ko);
});

export async function load(vrmPath) {
  const gltf = await parse(vrmPath);
  const vrm = gltf.userData.vrm;
  VRMUtils.rotateVRM0(vrm);
  return vrm;
}
export async function clip(path, vrm) {
  const g = await parse(path);
  return createVRMAnimationClip(g.userData.vrmAnimations[0], vrm);
}
export async function animation(path) {
  const g = await parse(path);
  return g.userData.vrmAnimations[0];
}

const down = new THREE.Vector3(0, -1, 0);
export function armAngle(vrm, side = 'left') {
  vrm.scene.updateMatrixWorld(true);
  const a = vrm.humanoid.getRawBoneNode(`${side}UpperArm`).getWorldPosition(new THREE.Vector3());
  const b = vrm.humanoid.getRawBoneNode(`${side}LowerArm`).getWorldPosition(new THREE.Vector3());
  return THREE.MathUtils.radToDeg(b.sub(a).normalize().angleTo(down));
}
export { THREE };
