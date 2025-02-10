#!/usr/bin/env python3
import traceback
import logging
import json
import os
import exif
import re
import sqlite3
from typing import Optional
from aiohttp import ClientSession, FormData
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler
)
from anthropic import Anthropic

CURRENT_MESSAGE_ID = None

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

def load_config(config_file="config.json"):

    if not os.path.exists(config_file):
        raise OSError(f"❌ Config file not found: {config_file}")

    with open(config_file, 'r') as f:
        config = json.load(f)

    if "telegram_bot" not in config:
        logger.error(f"❌ telegram_bot not available in config file: {config}")
        return False

    return config["telegram_bot"]

config = load_config()
client = None
if "ANTHROPIC_API_KEY" in config:
    client = Anthropic(api_key=config["ANTHROPIC_API_KEY"])

# Database setup
def setup_database():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS image_data (
        message_id INTEGER PRIMARY KEY,
        photo_file_id TEXT,
        legend TEXT,
        likes INTEGER DEFAULT 0
    )
    ''')
    conn.commit()
    conn.close()

setup_database()

def save_image_data(message_id: int, photo_file_id: str, legend: Optional[str]):
    """
    Save image data to the SQLite database.

    Args:
        message_id (int): The Telegram message ID.
        photo_file_id (str): The file ID of the photo.
        legend (Optional[str]): The caption of the photo, if any.
    """
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO image_data (message_id, photo_file_id, legend)
    VALUES (?, ?, ?)
    ''', (message_id, photo_file_id, legend))
    conn.commit()
    conn.close()

async def is_api_online() -> bool:
    try:
        async with ClientSession() as session:
            prompts_url = f"{config['api_url']}{config['api_methods']['prompts']}"
            async with session.get(prompts_url) as response:
                return response.status == 200
    except Exception as e:
        logger.error(f"Error checking API url: {e}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message when the command /start is issued."""
    if update.message:
        await update.message.reply_text(config["messages"]["welcome"])

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send info message when the command /info is issued."""
    if update.message:
        reply_text = config["messages"]["info"]

        is_online = await is_api_online()
        if is_online:
            reply_text += f"\n\n- API service available"
        else:
            reply_text += f"\n\n- API service offline"

        await update.message.reply_text(reply_text)

async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome new members when they join."""
    if update.message and update.message.new_chat_members:
        for new_member in update.message.new_chat_members:
            if not new_member.is_bot:
                await update.message.reply_text(
                    f"Welcome {new_member.mention_html()}!\n\n{config['messages']['welcome']}",
                    parse_mode='HTML'
                )

async def interrogate_image_with_api(image_data: bytes) -> Optional[str]:
    """Send image to API and get interrogator result."""
    try:
        async with ClientSession() as session:
            prompt_data = FormData()
            prompt_data.add_field(
                'image',
                image_data,
                filename='telegram_image.jpg'
            )
            interrogate_url = f"{config['api_url']}{config['api_methods']['interrogate']}"
            async with session.post(
                interrogate_url,
                data=prompt_data
            ) as response:
                if response.status == 404:
                    return "Sorry this api call is not available"
                if response.status == 200:
                    return await response.read()
                logger.error(f"API request failed with status {response.status}")
                return None
    except Exception as e:
        logger.error(f"Error processing image with API: {e}")
        return None

async def process_image_with_api(image_data: bytes, prompt: str) -> Optional[bytes]:
    """Send image and prompt to API and get processed image back."""
    try:
        async with ClientSession() as session:
            prompt_data = FormData()
            prompt_data.add_field('prompt-text', prompt)
            prompt_data.add_field(
                'image',
                image_data,
                filename='telegram_image.jpg'
            )
            gen_url = f"{config['api_url']}{config['api_methods']['gen']}"
            async with session.post(
                gen_url,
                data=prompt_data
            ) as response:
                if response.status == 404:
                    return "Sorry this prompt is not available"
                if response.status == 200:
                    return await response.read()
                logger.error(f"API request failed with status {response.status}")
                return None
    except Exception as e:
        logger.error(f"Error processing image with API: {e}")
        return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages."""
    if not update.message:
        return

    # Check if api online
    is_online = await is_api_online()
    if not is_online:
        await update.message.reply_text(
            "❌ API server is not online"
        )
        return

    # Check if message contains an image
    if not update.message.photo:
        await update.message.reply_text(
            "🖼️ Please send an image along with your text prompt!"
        )
        return

    # Get the largest version of the photo
    photo = update.message.photo[-1]
    legend = update.message.caption

    # Send "processing" message
    processing_msg = await update.message.reply_text(
        "📇 Processing your image... Please wait."
    )

    try:
        # Download the photo
        photo_file = await context.bot.get_file(photo.file_id)
        photo_bytes = await photo_file.download_as_bytearray()

        # interrogate the image
        interrogator_prompt = await interrogate_image_with_api(photo_bytes)

        if client:
            message_content = [
                "You are an AI assistant tasked with processing messages from a Telegram channel and generating Stable Diffusion prompts based on the content. Each message contains a photo and a legend. Your job is to analyze both elements and create a prompt that will modify the original photo using Stable Diffusion.\n",
                "You will receive two inputs:\n",
                "<photo>\n",
                str(interrogator_prompt),
                "</photo>\n",
                "<legend>\n",
                str(legend),
                "</legend>\n",
                "Follow these steps to process the inputs and generate a Stable Diffusion prompt:\n",
                "1. Analyze the photo:\n",
                "   - Describe the main elements, subjects, and overall composition of the image.\n",
                "   - Note any distinctive features, colors, or styles present in the photo.\n",
                "2. Interpret the legend:\n",
                "   - Identify key words, themes, or concepts mentioned in the legend.\n",
                "   - Determine the mood, tone, or atmosphere suggested by the text.\n",
                "3. Combine photo analysis and legend interpretation:\n",
                "   - Find connections between the visual elements in the photo and the ideas expressed in the legend.\n",
                "   - Identify aspects of the photo that could be enhanced or modified based on the legend.\n",
                "4. Generate a Stable Diffusion prompt:\n",
                "   - Start with a clear description of the main subject or scene from the original photo.\n",
                "   - Replace the main subject by one or many pudgy penguins, or if not possible, include one pudgy penguin visual element.\n"
                "   - DO NOT put bow tie on the  penguin.\n"
                "   - Incorporate elements from the legend to guide the modification or enhancement of the image.\n",
                "   - Use specific, descriptive language to convey the desired style, mood, and visual elements.\n",
                "   - Include any relevant techniques, or references that align with the legend and original photo.\n",
                "5. Refine and optimize the prompt:\n",
                "   - Ensure the prompt is clear, concise, and focused.\n",
                "   - Use Stable Diffusion-friendly terminology and structure.\n",
                "   - Balance faithfulness to the original photo with creative interpretation of the legend.\n",
                "Provide your output in the following format:\n",
                "<analysis>\n",
                "[Your analysis of the photo and legend]\n",
                "</analysis>\n",
                "<stable_diffusion_prompt>\n",
                "[Your generated Stable Diffusion prompt]\n",
                "</stable_diffusion_prompt>\n",
                "Remember to create a prompt that will result in a modified version of the original photo, incorporating elements from the legend while maintaining the essence of the original image."
            ]

            # DEBUG:
            #await update.message.reply_text(
            #    "".join(message_content)
            #)

            # ask Claude to build prompt,
            try:
                message = client.messages.create(
                    max_tokens=1024,
                    messages=[
                        {
                            "role": "user",
                            "content": str("".join(message_content))
                        }
                    ],
                    model="claude-3-5-sonnet-latest",
                )

                logger.info(message)
                logger.info(message.content)

                # await update.message.reply_text(
                #     str(message.content[0])
                # )

                pattern = r'<stable_diffusion_prompt>(.*?)</stable_diffusion_prompt>'
                match = re.search(pattern, str(message.content[0]), re.DOTALL)
                if match:
                    api_call_prompt = match.group(1).strip()
                else:
                    raise ValueError("No stable_diffusion_prompt found in the content")
            except Exception as e:
                logger.error(f"Error during anthropic request: {e}")
                logger.error(traceback.format_exc())
                api_call_prompt = f"{legend}, {interrogator_prompt}"
        else:
            api_call_prompt = f"{legend}, {interrogator_prompt}"

        # Send "prompt" message, keep prompt_msg to delete it later
        # prompt_msg = await update.message.reply_text(
        #     f"📇 Processing your image using this prompt: {api_call_prompt}"
        # )

        result_image = await process_image_with_api(photo_bytes, api_call_prompt)
        await processing_msg.delete()

        # TODO read prompt from exif data
        # exif_image = exif.Image(result_image)
        # if exif_image.has_exif and "prompt" in dir(exif_image):
        #     response_caption = exif_image['prompt']

        # Delete the prompt message
        # await prompt_msg.delete()

        if result_image:
            await update.message.reply_photo(
                result_image,
                caption=api_call_prompt.replace('\n', '')
            )
        else:
            await update.message.reply_text(
                "Sorry, there was an error processing your image. Please try again later."
            )

    except Exception as e:
        logger.error(f"Error handling message: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text(
            "Sorry, something went wrong. Please try again later."
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages."""
    if not update.message:
        return

    # Check if api online
    is_online = await is_api_online()
    if not is_online:
        await update.message.reply_text(
            "❌ API server is not online"
        )
        return

    # Check if message contains an image
    if not update.message.photo:
        await update.message.reply_text(
            "🖼️ Please send an image along with your text prompt!"
        )
        return

    # Get the largest version of the photo
    CURRENT_MESSAGE_ID = update.message.message_id
    current_photo_file_id = update.message.photo[-1].file_id
    current_legend = update.message.caption

    # Save parameters in SQLite database with id set to message id
    save_image_data(CURRENT_MESSAGE_ID, current_photo_file_id, current_legend)

    # process image
    process_image(update, context, current_photo_file_id, current_legend)


def like_message(message_id) -> None:
    try:
        # Fetch the message from the database
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()

        # Add a like counter for each message
        cursor.execute('''
        UPDATE image_data
        SET likes = likes + 1
        WHERE message_id = ?
        ''', (message_id,))

        conn.commit()

    except Exception as e:
        logger.error(f"Error in like_message: {str(e)}")
    finally:
        conn.close()

async def like_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler for the /like command. Add 1 to like counter based on the provided message ID.

    Usage: /like <message_id>
    """
    try:
        # Extract the message ID from the command arguments
        message_id = int(context.args[0]) if context.args else None

        if not message_id:
            if CURRENT_MESSAGE_ID is not None:
                message_id = CURRENT_MESSAGE_ID
            else:
                await update.message.reply_text("Please provide a valid message ID. Usage: /like <message_id>")
                return

        like_message(message_id)

        # Fetch the updated like count
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute('SELECT likes FROM image_data WHERE message_id = ?', (message_id,))
        result = cursor.fetchone()

        if result:
            likes = result[0]
            await update.message.reply_text(f"👍 Like added! Total likes: {likes}")
        else:
            await update.message.reply_text(f"Message with ID {message_id} not found.")

    except ValueError:
        await update.message.reply_text("Please provide a valid message ID. Usage: /like <message_id>")
    except Exception as e:
        logger.error(f"Error in like_command: {str(e)}")
        await update.message.reply_text("An error occurred while processing your request.")
    finally:
        conn.close()
def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(config["bot_token"]).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("info", info))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_member))
    application.add_handler(MessageHandler(filters.PHOTO, handle_message))

    # Start the Bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
