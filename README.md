# Prompt Inspector 🔎
Inspect prompts 🔎 from images uploaded to discord

## Functionality

This Discord bot reacts to any image with generation metadata from Automatic1111's WebUI.
If generation metadata is detected, a magnifying glass react is added to the image. If the user
clicks the magnifying glass, an embed is generated with the image generation settings.

## Setup

1. Clone the repository
2. Install the dependencies with `pip install -r requirements.txt`
3. Create a Discord bot and invite it to your server
4. Enable the `Message Content Intent` in the Discord developer portal
5. Create a file named ".env" in the root directory of the project
6. Set `BOT_TOKEN=<your discord bot token>` in the .env file
7. Add the channel IDs you want the bot to work in into the `config.toml` file
8. Run the bot with `python3 PromptInspector.py`

## Examples
![Example 1](images/2023-03-09_00-14.png)
![Example 2](images/2023-03-09_00-14_1.png)