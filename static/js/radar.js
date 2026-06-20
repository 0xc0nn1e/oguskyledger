// 共用雷達背景（Three.js）：同心圓 + 十字 + 旋轉掃描 wedge，純背景唔載 data。
// 畀冇自己 page JS 嘅頁面用（例：login）。有自己 radar 嘅頁（home/stats/about/
// details）各自喺 page JS inline init，唔經呢度。
// 有 #radar canvas 先 init，冇就乖乖唔做嘢。
import * as THREE from 'three';

const canvas = document.getElementById('radar');
if (canvas) {
  const MINT = 0x7fffd4, RING = 0x1f5a4a;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, innerWidth / innerHeight, 0.1, 200);
  camera.position.set(0, 8, 14); camera.lookAt(0, 0, 0);
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setSize(innerWidth, innerHeight);
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));

  for (const r of [2, 4, 6, 8, 10]) {
    scene.add(new THREE.Mesh(
      new THREE.RingGeometry(r - 0.01, r + 0.01, 96),
      new THREE.MeshBasicMaterial({ color: RING, transparent: true, opacity: 0.5, side: THREE.DoubleSide })
    )).rotation.x = -Math.PI / 2;
  }
  scene.add(new THREE.LineSegments(
    new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(-10, 0, 0), new THREE.Vector3(10, 0, 0),
      new THREE.Vector3(0, 0, -10), new THREE.Vector3(0, 0, 10),
    ]),
    new THREE.LineBasicMaterial({ color: RING, transparent: true, opacity: 0.35 })
  ));

  const sweepGroup = new THREE.Group();
  sweepGroup.add(new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, 0), new THREE.Vector3(10, 0, 0)]),
    new THREE.LineBasicMaterial({ color: MINT, transparent: true, opacity: 0.7 })
  ));
  const wedge = new THREE.Mesh(
    new THREE.CircleGeometry(10, 48, -Math.PI / 4, Math.PI / 4),
    new THREE.MeshBasicMaterial({ color: MINT, transparent: true, opacity: 0.08, side: THREE.DoubleSide })
  );
  wedge.rotation.x = -Math.PI / 2;
  sweepGroup.add(wedge);
  scene.add(sweepGroup);

  addEventListener('resize', () => {
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
  });
  (function animate() {
    sweepGroup.rotation.y -= 0.012;
    renderer.render(scene, camera);
    requestAnimationFrame(animate);
  })();
}
