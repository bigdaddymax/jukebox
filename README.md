## Current version

Version v3 is 4 buttons, navigation through folders (prev/next) and videos in folders (prev/next)

This version also supports web control, it runs on 8080 port and allows to show what is currently playing and play selected video.
The web navigator allows to display screenshot (should be the same name as the video file), if not present script will generate screenshots automatically.

## Needed for Raspberry Zero 1

Preparing video for uploading: split mp4 to two files: video h264 and audio wav

yt-dlp -f "bestvideo+bestaudio/best" URL_ВІДЕО -o "temp_video.mp4" && \
ffmpeg -i temp_video.mp4 -an -vcodec libx264 -crf 20 -pix_fmt yuv420p -f h264 output.h264 && \
ffmpeg -i temp_video.mp4 -vn -acodec pcm_s16le -ar 44100 output.wav && \
rm temp_video.mp4

## For Raspberry Zero 2

Download video in max 1080x720 resolution, create mp4 with embedded subtitles

yt-dlp --force-overwrites -i \
  -f "bv*[height<=1080]+ba/b" \
  --ffmpeg-location /usr/bin/ffmpeg \
  --postprocessor-args "VideoConvertor:-vf scale=-2:720 -pix_fmt yuv420p" \
  --recode-video mp4 \
  --write-subs --write-auto-subs --sub-langs "en" \
  --embed-subs \
  -o "%(title)s.%(ext)s" "https://www.youtube.com/watch?v=vQUr3VVUmPY"
