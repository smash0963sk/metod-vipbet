import React, { useEffect, useState } from "react";
import { AbsoluteFill, Audio, continueRender, delayRender, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { buildFrame } from "./engine/scene";

// Шрифты подгружаются до первого кадра
const useFonts = () => {
  const [handle] = useState(() => delayRender("fonts"));
  useEffect(() => {
    const fonts = [
      new FontFace("IDB", `url(${staticFile("InterDisplay-Black.otf")})`),
      new FontFace("IDE", `url(${staticFile("InterDisplay-ExtraBold.otf")})`),
    ];
    Promise.all(fonts.map(f => f.load()))
      .then(loaded => { loaded.forEach(f => document.fonts.add(f)); continueRender(handle); })
      .catch(() => continueRender(handle));
  }, [handle]);
};

export const Episode = ({ ep, tl, audio }) => {
  useFonts();
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const svg = ep ? buildFrame(ep, tl, frame / fps) : "";
  return (
    <AbsoluteFill style={{ backgroundColor: (ep && ep.bg) || "#FBE2BC" }}>
      <div dangerouslySetInnerHTML={{ __html: svg }} />
      {audio ? <Audio src={staticFile(audio)} /> : null}
    </AbsoluteFill>
  );
};
