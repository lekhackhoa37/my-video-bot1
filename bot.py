import logging
import os
import asyncio # Thư viện asyncio cần thiết cho các hàm bất đồng bộ
import time
from telegram import Update # type: ignore
from telegram.ext import Application, MessageHandler, filters, ContextTypes # type: ignore

# --- Phần Cấu hình Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Phần Lấy Thông Tin Cấu Hình Từ Biến Môi Trường ---
BOT_TOKEN = os.environ.get('BOT_TOKEN')
SOURCE_GROUP_ID_STR = os.environ.get('SOURCE_GROUP_ID')
TARGET_GROUP_ID_STR = os.environ.get('TARGET_GROUP_ID')

SOURCE_GROUP_ID = None
if SOURCE_GROUP_ID_STR:
    try:
        SOURCE_GROUP_ID = int(SOURCE_GROUP_ID_STR)
    except ValueError:
        logger.error(f"Lỗi: SOURCE_GROUP_ID ('{SOURCE_GROUP_ID_STR}') không phải là số nguyên hợp lệ.")

TARGET_GROUP_ID = None
if TARGET_GROUP_ID_STR:
    try:
        TARGET_GROUP_ID = int(TARGET_GROUP_ID_STR)
    except ValueError:
        logger.error(f"Lỗi: TARGET_GROUP_ID ('{TARGET_GROUP_ID_STR}') không phải là số nguyên hợp lệ.")

logger.info(f"BOT_TOKEN đã được nạp (kiểm tra độ dài): {len(BOT_TOKEN) if BOT_TOKEN else 'CHƯA ĐẶT'}")
logger.info(f"SOURCE_GROUP_ID từ biến môi trường là: {SOURCE_GROUP_ID if SOURCE_GROUP_ID is not None else 'CHƯA ĐẶT hoặc LỖI CHUYỂN ĐỔI'}")
logger.info(f"TARGET_GROUP_ID từ biến môi trường là: {TARGET_GROUP_ID if TARGET_GROUP_ID is not None else 'CHƯA ĐẶT hoặc LỖI CHUYỂN ĐỔI'}")

# --- Phần Xử Lý Danh Sách Video Đã Gửi ---
PROCESSED_VIDEOS_FILE = "processed_videos.txt"
processed_video_unique_ids = set()

def load_processed_videos():
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
    processed_video_unique_ids.add(video_unique_id)
    try:
        with open(PROCESSED_VIDEOS_FILE, "a") as f:
            f.write(video_unique_id + "\n")
    except Exception as e:
        logger.error(f"Lỗi khi lưu ID video {video_unique_id} vào file: {e}")

async def process_and_send_video(context: ContextTypes.DEFAULT_TYPE, file_id: str, file_unique_id: str, original_message_id_for_log="N/A"):
    if file_unique_id in processed_video_unique_ids:
        logger.info(f"Video {file_unique_id} (từ tin nhắn gốc ID: {original_message_id_for_log}) đã được xử lý. Bỏ qua.")
        return

    try:
        logger.info(f"Đang chuẩn bị gửi video {file_unique_id} (từ tin nhắn gốc ID: {original_message_id_for_log}) đến nhóm {TARGET_GROUP_ID}...")
        await context.bot.send_video(chat_id=TARGET_GROUP_ID, video=file_id) # Gửi không caption
        logger.info(f"ĐÃ GỬI THÀNH CÔNG video {file_unique_id} đến nhóm {TARGET_GROUP_ID}.")
        save_processed_video_id(file_unique_id)
        await asyncio.sleep(2) # Dùng asyncio.sleep cho hàm async
    except error.RetryAfter as e: # telegram.error.RetryAfter
        logger.warning(f"Bị Telegram yêu cầu thử lại sau {e.retry_after} giây. Đang tạm dừng...")
        await asyncio.sleep(e.retry_after)
        await process_and_send_video(context, file_id, file_unique_id, original_message_id_for_log) # Thử gửi lại
    except Exception as e:
        logger.error(f"Lỗi nghiêm trọng khi gửi video {file_unique_id} đến nhóm {TARGET_GROUP_ID}: {e}")

async def video_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    
    if SOURCE_GROUP_ID is None or TARGET_GROUP_ID is None:
        if not hasattr(context.bot_data, 'missing_id_logged_video_handler'): # Log một lần
            logger.error("SOURCE_GROUP_ID hoặc TARGET_GROUP_ID không được cấu hình đúng trong video_message_handler.")
            context.bot_data['missing_id_logged_video_handler'] = True
        return

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
        await process_and_send_video(context, video_to_process_file_id, video_to_process_file_unique_id, original_message_id)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f'Update "{update}" gây ra lỗi "{context.error}"')


def main() -> None:
    if not BOT_TOKEN:
        logger.error("LỖI NGHIÊM TRỌNG: Biến môi trường BOT_TOKEN chưa được đặt. Bot không thể chạy.")
        return
    if SOURCE_GROUP_ID is None:
        logger.error("LỖI NGHIÊM TRỌNG: Biến môi trường SOURCE_GROUP_ID chưa được đặt hoặc giá trị không hợp lệ. Bot không thể chạy.")
        return
    if TARGET_GROUP_ID is None:
        logger.error("LỖI NGHIÊM TRỌNG: Biến môi trường TARGET_GROUP_ID chưa được đặt hoặc giá trị không hợp lệ. Bot không thể chạy.")
        return

    load_processed_videos()

    # Thay thế Updater và Dispatcher bằng Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Bộ lọc (filters) mới
    # filters.VIDEO cho video gửi trực tiếp
    # filters.Document.VIDEO cho video gửi dưới dạng file (document)
    # Bạn có thể thêm các mime_type cụ thể nếu muốn: e.g. filters.Document.MimeType("video/mp4")
    media_filter = filters.VIDEO | filters.Document.VIDEO
    
    application.add_handler(MessageHandler(media_filter, video_message_handler))
    application.add_error_handler(error_handler)

    logger.info("Bot đang khởi động và chuẩn bị lắng nghe tin nhắn (phiên bản thư viện mới)...")
    # Chạy bot (polling)
    # drop_pending_updates=True nghĩa là bỏ qua các update nhận được khi bot offline
    # Nếu muốn xử lý update cũ (khi bot offline), đặt là False (mặc định là False)
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)
    # application.idle() không còn cần thiết khi dùng run_polling trong kịch bản đơn giản này,
    # vì run_polling() sẽ block cho đến khi bot dừng.

if __name__ == '__main__':
    main()
