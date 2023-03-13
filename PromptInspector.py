import io
import os
import toml

from discord import Client, Intents, Embed, ButtonStyle
from discord.ui import View, button
from dotenv import load_dotenv
from PIL import Image

load_dotenv()
MONITORED_CHANNEL_IDS = toml.load('config.toml')['MONITORED_CHANNEL_IDS']

intents = Intents.default()
intents.message_content = True
intents.members = True
client = Client(intents=intents)


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


def get_embed(embed_dict, context):
    embed = Embed()
    for key, value in embed_dict.items():
        embed.add_field(name=key, value=value)
    pfp = context.author.avatar if context.author.avatar else context.author.default_avatar_url
    embed.set_footer(text=f'Original post by {context.author}', icon_url=pfp)
    return embed


@client.event
async def on_ready():
    print(f"Logged in as {client.user}!")


@client.event
async def on_message(message):
    if message.channel.id in MONITORED_CHANNEL_IDS and message.attachments:
        for attachment in message.attachments:
            if attachment.content_type.startswith("image/"):
                image_data = await attachment.read()
                with Image.open(io.BytesIO(image_data)) as img:
                    try:
                        metadata = img.info
                        metadata = metadata['parameters']
                        get_embed(get_params_from_string(metadata), message)
                        await message.add_reaction('🔎')
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


@client.event
async def on_raw_reaction_add(ctx):
    if ctx.emoji.name == '🔎':
        channel = client.get_channel(ctx.channel_id)
        message = await channel.fetch_message(ctx.message_id)
        if not message:
            return
        if message.channel.id in MONITORED_CHANNEL_IDS and message.attachments and ctx.user_id != client.user.id:
            for attachment in message.attachments:
                if attachment.content_type.startswith("image/"):
                    image_data = await attachment.read()
                    with Image.open(io.BytesIO(image_data)) as img:
                        try:
                            metadata = img.info
                            metadata = metadata['parameters']
                            embed = get_embed(get_params_from_string(metadata), message)
                            embed.set_image(url=attachment.url)
                            user_dm = await client.get_user(ctx.user_id).create_dm()
                            custom_view = MyView()
                            custom_view.metadata = metadata
                            await user_dm.send(view=custom_view, embed=embed, mention_author=False)
                        except:
                            pass


client.run(os.environ["BOT_TOKEN"])
