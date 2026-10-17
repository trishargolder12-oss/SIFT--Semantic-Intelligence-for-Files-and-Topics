// The same source coordinate system as the 1690 × 931 room artwork.
// This homography maps all four screenshot corners onto the illustrated screen.
export function LaptopScreen() {
  return <div className="laptop-scene" aria-hidden="true"><svg className="laptop-canvas" viewBox="0 0 1690 931" width="1690" height="931" focusable="false">
    <defs><clipPath id="laptop-visible-screen"><path d="M946 220L1533 191Q1543 190 1543 204L1545 518C1515 513 1485 519 1466 539L1447 560L1427 550L1413 556L1399 550L1384 558L1365 548L1350 536L1339 539L1349 556L1329 553L1320 565L919 556L933 233Q934 222 946 220Z" /></clipPath></defs>
    <g clipPath="url(#laptop-visible-screen)"><foreignObject x="0" y="0" width="1690" height="931"><div className="screen-projection"><img className="actual-app-screen" src="/assets/library-preview.png" width="1200" height="820" alt="" draggable="false" /></div></foreignObject></g>
  </svg></div>;
}
