declare module 'wav-encoder' {
  export interface WavEncoderOptions {
    sampleRate: number;
    channelData: Float32Array[];
  }

  export function encode(options: WavEncoderOptions): Promise<ArrayBuffer>;
}