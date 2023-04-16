import io
import os
import toml
import asyncio

from discord import Client, Intents, Embed, ButtonStyle, Message, Attachment, File, Embed, Member, RawReactionActionEvent, ApplicationContext
from discord.ext import commands
from discord.ui import View, button
from dotenv import load_dotenv
from PIL import Image
from collections import OrderedDict

load_dotenv()
CONFIG = toml.load('config.toml')
MONITORED_CHANNEL_IDS = CONFIG.get('MONITORED_CHANNEL_IDS', [])
SCAN_LIMIT_BYTES = CONFIG.get('SCAN_LIMIT_BYTES', 10 * 1024**2)  # Default 10 MB

intents = Intents.default() | Intents.message_content | Intents.members
client = commands.Bot(intents=intents)


def get_params_from_string(param_str):
    output_dict = {}
    parts = param_str.split('Steps: ')
    prompts = parts[0]
    params = 'Steps: ' + parts[1]
    if 'Negative prompt: ' in prompts:
        output_dict['Prompt'] = prompts.split('Negative prompt: ')[0]
        output_dict['Negative Prompt'] = prompts.split('Negative prompt: ')[1]
        if len(output_dict['Negative Prompt']) > 1000:
            output_dict['Negative Prompt'] = output_dict['Negative Prompt'][:1000] + '...'
    else:
        output_dict['Prompt'] = prompts
    if len(output_dict['Prompt']) > 1000:
      output_dict['Prompt'] = output_dict['Prompt'][:1000] + '...'
    params = params.split(', ')
    for param in params:
        try:
            key, value = param.split(': ')
            output_dict[key] = value
        except ValueError:
            pass
    return output_dict


def get_embed(embed_dict, context: Message):
    embed = Embed(color=context.author.color)
    for key, value in embed_dict.items():
        embed.add_field(name=key, value=value, inline='Prompt' not in key)
    pfp = context.author.avatar if context.author.avatar else context.author.default_avatar_url
    embed.set_footer(text=f'Posted by {context.author}', icon_url=pfp)
    return embed


def read_info_from_image_stealth(image):
    # trying to read stealth pnginfo
    width, height = image.size
    pixels = image.load()

    binary_data = ''
    buffer = ''
    index = 0
    sig_confirmed = False
    confirming_signature = True
    reading_param_len = False
    reading_param = False
    read_end = False
    if len(pixels[0, 0]) < 4:
        return None
    for x in range(width):
        for y in range(height):
            _, _, _, a = pixels[x, y]
            buffer += str(a & 1)
            if confirming_signature:
                if index == len('stealth_pnginfo') * 8 - 1:
                    if buffer == ''.join(format(byte, '08b') for byte in 'stealth_pnginfo'.encode('utf-8')):
                        confirming_signature = False
                        sig_confirmed = True
                        reading_param_len = True
                        buffer = ''
                        index = 0
                    else:
                        read_end = True
                        break
            elif reading_param_len:
                if index == 32:
                    param_len = int(buffer, 2)
                    reading_param_len = False
                    reading_param = True
                    buffer = ''
                    index = 0
            elif reading_param:
                if index == param_len:
                    binary_data = buffer
                    read_end = True
                    break
            else:
                # impossible
                read_end = True
                break

            index += 1
        if read_end:
            break

    if sig_confirmed and binary_data != '':
        # Convert binary string to UTF-8 encoded text
        decoded_data = bytearray(int(binary_data[i:i + 8], 2) for i in range(0, len(binary_data), 8)).decode('utf-8',errors='ignore')
        return decoded_data
    return None


@client.event
async def on_ready():
    print(f"Logged in as {client.user}!")


@client.event
async def on_message(message: Message):
    if message.channel.id in MONITORED_CHANNEL_IDS and message.attachments:
        attachments = [a for a in message.attachments if a.filename.lower().endswith(".png") and a.size < SCAN_LIMIT_BYTES]
        for attachment in attachments:
            image_data = await attachment.read()
            with Image.open(io.BytesIO(image_data)) as img:
                try:
                    info = read_info_from_image_stealth(img)
                    if info and 'Steps' in info:
                        await message.add_reaction('🔎')
                        return
                except:
                    pass


class MyView(View):
    def __init__(self):
        super().__init__(timeout=3600, disable_on_timeout=True)
        self.metadata = None

    @button(label='Full Parameters', style=ButtonStyle.green)
    async def details(self, button, interaction):
        button.disabled = True
        await interaction.response.edit_message(view=self)
        if len(self.metadata) > 1980:
          for i in range(0, len(self.metadata), 1980):
            await interaction.followup.send(f"```yaml\n{self.metadata[i:i+1980]}```")
        else:
          await interaction.followup.send(f"```yaml\n{self.metadata}```")


async def read_attachment_metadata(i: int, attachment: Attachment, metadata: OrderedDict):
    """Allows downloading in bulk"""
    try:
        image_data = await attachment.read()
        with Image.open(io.BytesIO(image_data)) as img:
            info = read_info_from_image_stealth(img)
            if info and "Steps" in info:
                metadata[i] = info
    except Exception as error:
        print(f"{type(error).__name__}: {error}")


@client.event
async def on_raw_reaction_add(ctx: RawReactionActionEvent):
    """Send image metadata in reacted post to user DMs"""
    if ctx.emoji.name != '🔎' or ctx.channel_id not in MONITORED_CHANNEL_IDS or ctx.member.bot:
        return
    channel = client.get_channel(ctx.channel_id)
    message = await channel.fetch_message(ctx.message_id)
    if not message:
        return
    attachments = [a for a in message.attachments if a.filename.lower().endswith(".png")]
    if not attachments:
        return
    metadata = OrderedDict()
    tasks = [read_attachment_metadata(i, attachment, metadata) for i, attachment in enumerate(attachments)]
    await asyncio.gather(*tasks)
    if not metadata:
        return
    user_dm = await client.get_user(ctx.user_id).create_dm()
    for attachment, data in [(attachments[i], data) for i, data in metadata.items()]:
        try:
            embed = get_embed(get_params_from_string(data), message)
            embed.set_image(url=attachment.url)
            custom_view = MyView()
            custom_view.metadata = metadata
            await user_dm.send(view=custom_view, embed=embed, mention_author=False)
        except:
            pass


@client.message_command(name="View Parameters")
async def message_command(ctx: ApplicationContext, message: Message):
    """Get raw list of parameters for every image in this post."""
    attachments = [a for a in message.attachments if a.filename.lower().endswith(".png")]
    if not attachments:
        await ctx.respond("This post contains no matching images.", ephemeral=True)
        return
    await ctx.defer(ephemeral=True)
    metadata = OrderedDict()
    tasks = [read_attachment_metadata(i, attachment, metadata) for i, attachment in enumerate(attachments)]
    await asyncio.gather(*tasks)
    if not metadata:
        await ctx.respond(f"This post contains no image generation data.\n{message.author.mention} needs to install [this extension](<https://github.com/ashen-sensored/sd_webui_stealth_pnginfo>).", ephemeral=True)
        return
    response = "\n\n".join(metadata.values())
    if len(response) < 1980:
        await ctx.respond(f"```yaml\n{response}```", ephemeral=True)
    else:
        with io.StringIO() as f:
            f.write(response)
            f.seek(0)
            await ctx.respond(file=File(f, "parameters.yaml"), ephemeral=True)


client.run(os.environ["BOT_TOKEN"])
