const VIDEO_EXT = /\.(mp4|webm|mov|m4v|avi|mkv)$/i;

export type MediaType = "image" | "video";

export function mediaTypeOf(filename: string): MediaType {
  return VIDEO_EXT.test(filename) ? "video" : "image";
}

export function isVideoUrl(url: string | null | undefined): boolean {
  return !!url && VIDEO_EXT.test(url);
}