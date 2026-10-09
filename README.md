## This is not needed for V2 version as we use hardware video processing available on Rapberry Zero 2

Preparing video for uploading: split mp4 to two files: video h264 and audio wav

yt-dlp -f "bestvideo+bestaudio/best" URL_ВІДЕО -o "temp_video.mp4" && \
ffmpeg -i temp_video.mp4 -an -vcodec libx264 -crf 20 -pix_fmt yuv420p -f h264 output.h264 && \
ffmpeg -i temp_video.mp4 -vn -acodec pcm_s16le -ar 44100 output.wav && \
rm temp_video.mp4
