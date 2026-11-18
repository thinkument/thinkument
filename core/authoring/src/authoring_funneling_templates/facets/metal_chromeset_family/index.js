import { defineAppPackV1 } from 'think-app';
import aesthetics from './aesthetics.js';

export function createMetalChromePackV1(chromeId) {
  return defineAppPackV1({ id: `metal_${chromeId}`, aesthetics });
}
