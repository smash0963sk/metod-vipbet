import React from "react";
import { Composition } from "remotion";
import { Episode } from "./Episode";

const FPS = 30;

export const Root = () => (
  <Composition
    id="Episode"
    component={Episode}
    fps={FPS}
    width={1080}
    height={1920}
    durationInFrames={FPS * 10}
    defaultProps={{ ep: null, tl: [], total: 10, audio: null }}
    calculateMetadata={({ props }) => ({ durationInFrames: Math.ceil((props.total || 10) * FPS) })}
  />
);
