import logging
import os
import time
from telegram import Update, error
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext

# --- Phần Cấu hình Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Phần Lấy Thông Tin Cấu Hình ---
# BOT_TOKEN vẫn bắt buộc phải lấy từ biến môi trường để đảm bảo an toàn
BOT_TOKEN = os.environ.get('BOT_TOKEN')

# ID nhóm nguồn và nhóm đích được xác định từ JSON bạn cung cấp
# Gán trực tiếp vào code để bạn dễ copy-paste.
# NHƯNG NHỚ: Khi deploy lên Render, bạn NÊN dùng biến môi trường cho cả các ID này.
SOURCE_GROUP_ID = -1001453035193  # ID của kênh "Đại Học DamDang 🔞 (@daihoc69)"
TARGET_GROUP_ID = -1002497993114  # ID của nhóm "Clip nyc 1"

# In ra để kiểm tra (bạn có thể xóa hoặc comment dòng này sau khi kiểm tra)
logger.info(f"SOURCE_GROUP_ID được gán là: {SOURCE_GROUP_ID}")
logger.info(f"TARGET_GROUP_ID được gán là: {TARGET_GROUP_ID}")


# --- Phần Xử Lý Danh Sách Video Đã Gửi ---
PROCESSED_VIDEOS_FILE = "processed_videos.txt"
processed_video_unique_ids = set()

def load_processed_videos():
    """Tải danh sách file_unique_id của các video đã xử lý từ file khi bot khởi động."""
    try:
        with open(PROCESSED_VIDEOS_FILE, "r") as f:
            for line in f:
                processed_video_unique_ids.add(line.strip())
        logger.info(f"Đã tải {len(processed_video_unique_ids)} ID video đã xử lý từ file.")
    except FileNotFoundError:
        logger.info(f"File {PROCESSED_VIDEOS_FILE} không tìm thấy. Bắt đầu với danh sách trống.")
    except Exception as e:
        logger.error(f"Lỗi khi tải danh sách video đã xử lý: {e}")

def save_processed_video_id(video_unique_id: str):
    """Lưu file_unique_id của video đã xử lý vào set trong bộ nhớ và ghi vào cuối file."""
    processed_video_unique_ids.add(video_unique_id)
    try:
        with open(PROCESSED_VIDEOS_FILE, "a") as f:
            f.write(video_unique_id + "\n")
    except Exception as e:
        logger.error(f"Lỗi khi lưu ID video {video_unique_id} vào file: {e}")

def process_and_send_video(context: CallbackContext, file_id: str, file_unique_id: str, original_message_id_for_log="N/A"):
    """Kiểm tra và gửi video nếu chưa được xử lý, có xử lý rate limit cơ bản."""
    if file_unique_id in processed_video_unique_ids:
        logger.info(f"Video {file_unique_id} (từ tin nhắn gốc ID: {original_message_id_for_log}) đã được xử lý. Bỏ qua.")
        return

    try:
        logger.info(f"Đang chuẩn bị gửi video {file_unique_id} (từ tin nhắn gốc ID: {original_message_id_for_log}) đến nhóm {TARGET_GROUP_ID}...")
        context.bot.send_video(chat_id=TARGET_GROUP_ID, video=file_id) # Gửi không caption
        logger.info(f"ĐÃ GỬI THÀNH CÔNG video {file_unique_id} đến nhóm {TARGET_GROUP_ID}.")
        save_processed_video_id(file_unique_id)
        time.sleep(2)
    except error.RetryAfter as e:
        logger.warning(f"Bị Telegram yêu cầu thử lại sau {e.retry_after} giây. Đang tạm dừng...")
        time.sleep(e.retry_after)
        process_and_send_video(context, file_id, file_unique_id, original_message_id_for_log)
    except Exception as e:
        logger.error(f"Lỗi nghiêm trọng khi gửi video {file_unique_id} đến nhóm {TARGET_GROUP_ID}: {e}")

def video_message_handler(update: Update, context: CallbackContext) -> None:
    """Xử lý tin nhắn video hoặc document là video."""
    message = update.message
    
    if not (message and message.chat_id == SOURCE_GROUP_ID):
        return

    video_to_process_file_id = None
    video_to_process_file_unique_id = None
    original_message_id = message.message_id

    if message.video:
        video_to_process_file_id = message.video.file_id
        video_to_process_file_unique_id = message.video.file_unique_id
        logger.info(f"Nhận video (video type) trong nhóm nguồn: file_id={video_to_process_file_id}, file_unique_id={video_to_process_file_unique_id}")
    elif message.document and message.document.mime_type and message.document.mime_type.startswith('video/'):
        video_to_process_file_id = message.document.file_id
        video_to_process_file_unique_id = message.document.file_unique_id
        logger.info(f"Nhận video (document type) trong nhóm nguồn: file_id={video_to_process_file_id}, file_unique_id={video_to_process_file_unique_id}")
    
    if video_to_process_file_id and video_to_process_file_unique_id:
        process_and_send_video(context, video_to_process_file_id, video_to_process_file_unique_id, original_message_id)

def error_handler(update: Update, context: CallbackContext) -> None:
    """Ghi lại lỗi nếu có."""
    logger.warning(f'Update "{update}" gây ra lỗi "{context.error}"')

def main() -> None:
    """Hàm này sẽ thiết lập và chạy bot."""
    if not BOT_TOKEN: # Chỉ cần kiểm tra BOT_TOKEN vì các ID nhóm đã gán trực tiếp
        logger.error("LỖI NGHIÊM TRỌNG: Thiếu biến môi trường BOT_TOKEN. Bot không thể chạy.")
        return
    
    if not isinstance(SOURCE_GROUP_ID, int) or not isinstance(TARGET_GROUP_ID, int):
        logger.error(f"LỖI: SOURCE_GROUP_ID ({SOURCE_GROUP_ID}) hoặc TARGET_GROUP_ID ({TARGET_GROUP_ID}) không phải là số nguyên hợp lệ.")
        return

    load_processed_videos()

    updater = Updater(BOT_TOKEN, use_context=True, drop_pending_updates=False)
    dispatcher = updater.dispatcher

    media_filter = Filters.video | (Filters.document & Filters.document.video)
    # Chỉ định dispatcher chỉ xử lý tin nhắn từ SOURCE_GROUP_ID cụ thể
    # bằng cách kiểm tra `message.chat_id == SOURCE_GROUP_ID` bên trong handler.
    # Hoặc, nếu muốn lọc chặt hơn ở dispatcher:
    # handler = MessageHandler(Filters.chat(chat_id=SOURCE_GROUP_ID) & media_filter, video_message_handler)
    # dispatcher.add_handler(handler)
    # Tuy nhiên, cách kiểm tra trong handler đơn giản và dễ hiểu hơn cho nhiều trường hợp.
    dispatcher.add_handler(MessageHandler(media_filter, video_message_handler))
    
    dispatcher.add_error_handler(error_handler)

    logger.info("Bot đang khởi động và chuẩn bị lắng nghe tin nhắn...")
    updater.start_polling()
    logger.info("BOT ĐÃ CHẠY! Đang chờ video mới...")
    updater.idle()

if __name__ == '__main__':
    main()