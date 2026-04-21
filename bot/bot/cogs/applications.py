import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

APPLICATIONS_CATEGORY_ID = int(os.getenv("APPLICATIONS_CATEGORY_ID", 0))
LOGS_CHANNEL_ID = int(os.getenv("LOGS_CHANNEL_ID", 0))
APPLICATIONS_CHANNEL_ID = int(os.getenv("APPLICATIONS_CHANNEL_ID", 0))
GUILD_ID = int(os.getenv("GUILD_ID", 0))
REVIEWER_ROLE_IDS = [
    int(r.strip())
    for r in os.getenv("REVIEWER_ROLE_IDS", "0").split(",")
    if r.strip().isdigit()
]

BANNER_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "banner.png")
if not os.path.exists(BANNER_PATH):
    BANNER_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "banner.gif")
    if not os.path.exists(BANNER_PATH):
        BANNER_PATH = None


def has_reviewer_role(member: discord.Member) -> bool:
    return any(role.id in REVIEWER_ROLE_IDS for role in member.roles)


# ──────────────────────────────────────────────
#  MODAL — форма заявки
# ──────────────────────────────────────────────
class ApplicationModal(discord.ui.Modal, title="Основная заявка"):
    nickname = discord.ui.TextInput(
        label="Ваш ник в игре",
        placeholder="Введите ник...",
        required=True,
        max_length=64,
    )
    static = discord.ui.TextInput(
        label="Статик #",
        placeholder="Введите статик...",
        required=True,
        max_length=32,
    )
    age = discord.ui.TextInput(
        label="Возраст ООС",
        placeholder="Введите возраст...",
        required=True,
        max_length=8,
    )
    rollback = discord.ui.TextInput(
        label="Откат стрельбы (без отката не принимаем!)",
        placeholder="Ссылка или описание...",
        required=True,
        max_length=256,
    )
    families = discord.ui.TextInput(
        label="Семьи в которых вы были.",
        placeholder="Перечислите семьи...",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=512,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        category = guild.get_channel(APPLICATIONS_CATEGORY_ID)

        # Создаём канал заявки
        channel_name = f"заявление-{interaction.user.name}"
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(
                read_messages=True, send_messages=False
            ),
            guild.me: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, manage_channels=True
            ),
        }
        for role_id in REVIEWER_ROLE_IDS:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True
                )

        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
        )

        # Пинг ролей рассматривающих
        reviewer_mentions = " ".join(
            f"<@&{rid}>" for rid in REVIEWER_ROLE_IDS
        )

        # Проверяем предыдущие заявки (ищем закрытые каналы с именем пользователя)
        prev_apps = "Заявок не найдено."

        embed = discord.Embed(
            title="Заявление",
            color=0xFFFF00,  # жёлтый — на рассмотрении
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="Ваш ник в игре", value=self.nickname.value, inline=False)
        embed.add_field(name="Статик #", value=self.static.value, inline=False)
        embed.add_field(name="Возраст ООС", value=self.age.value, inline=False)
        embed.add_field(
            name="Откат стрельбы (без отката не принимаем!)",
            value=self.rollback.value,
            inline=False,
        )
        embed.add_field(
            name="Семьи в которых вы были.", value=self.families.value, inline=False
        )
        embed.add_field(
            name="Пользователь", value=interaction.user.mention, inline=False
        )
        embed.add_field(name="Username", value=interaction.user.name, inline=True)
        embed.add_field(name="ID", value=str(interaction.user.id), inline=True)

        view = ApplicationActionView(applicant=interaction.user)

        header = f"{reviewer_mentions}\n**Предыдущие заявки:**\n{prev_apps}"
        await ticket_channel.send(content=header, embed=embed, view=view)

        await interaction.followup.send(
            f"✅ Ваша заявка создана: {ticket_channel.mention}", ephemeral=True
        )


# ──────────────────────────────────────────────
#  MODAL — причина отказа
# ──────────────────────────────────────────────
class RejectModal(discord.ui.Modal, title="Причина отказа"):
    reason = discord.ui.TextInput(
        label="Укажите причину отказа",
        placeholder="Причина...",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=512,
    )

    def __init__(self, applicant: discord.Member, ticket_channel: discord.TextChannel):
        super().__init__()
        self.applicant = applicant
        self.ticket_channel = ticket_channel

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        # DM заявителю
        try:
            dm_embed = discord.Embed(
                title="Отклонение заявки",
                color=0xFF0000,
            )
            dm_embed.add_field(
                name="",
                value="**Ваша заявка в GLORY отклонена!**",
                inline=False,
            )
            dm_embed.add_field(
                name="ID Дискорд сервера",
                value=f"**{interaction.guild.id}**",
                inline=False,
            )
            dm_embed.add_field(
                name="Причина",
                value=self.reason.value,
                inline=False,
            )
            dm_embed.add_field(
                name="",
                value="Лог вашей заявки был записан в нашу базу данных.",
                inline=False,
            )
            dm_embed.timestamp = datetime.utcnow()
            await self.applicant.send(embed=dm_embed)
        except discord.Forbidden:
            pass

        # Лог
        await send_log(
            guild=interaction.guild,
            applicant=self.applicant,
            status="rejected",
            reviewer=interaction.user,
            reason=self.reason.value,
            channel=self.ticket_channel,
        )

        await interaction.followup.send("❌ Заявка отклонена. Канал будет удалён через 5 секунд.")
        import asyncio
        await asyncio.sleep(5)
        await self.ticket_channel.delete(reason="Заявка отклонена")


# ──────────────────────────────────────────────
#  MODAL — выбор войса для обзвона
# ──────────────────────────────────────────────
class CallModal(discord.ui.Modal, title="Вызов на обзвон"):
    voice_channel = discord.ui.TextInput(
        label="Название или ссылка на войс канал",
        placeholder="Например: 🔊 Собеседование #1",
        required=True,
        max_length=128,
    )

    def __init__(self, applicant: discord.Member):
        super().__init__()
        self.applicant = applicant

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            dm_embed = discord.Embed(
                title="📞 Вызов на обзвон",
                color=0x5865F2,
            )
            dm_embed.add_field(
                name="",
                value=f"**{interaction.user.mention} вызывает вас на обзвон по вашей заявке в GLORY!**",
                inline=False,
            )
            dm_embed.add_field(
                name="Войс канал",
                value=f"**{self.voice_channel.value}**",
                inline=False,
            )
            dm_embed.add_field(
                name="ID Дискорд сервера",
                value=f"**{interaction.guild.id}**",
                inline=False,
            )
            dm_embed.timestamp = datetime.utcnow()
            await self.applicant.send(embed=dm_embed)
        except discord.Forbidden:
            pass

        await interaction.followup.send(
            f"📞 {self.applicant.mention}, вас вызывают на обзвон в **{self.voice_channel.value}**!"
        )


# ──────────────────────────────────────────────
#  VIEW — кнопки в тикете заявки
# ──────────────────────────────────────────────
class ApplicationActionView(discord.ui.View):
    def __init__(self, applicant: discord.Member):
        super().__init__(timeout=None)
        self.applicant = applicant

    @discord.ui.button(
        label="Принять",
        style=discord.ButtonStyle.success,
        custom_id="app_accept",
    )
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_reviewer_role(interaction.user):
            await interaction.response.send_message(
                "❌ У вас нет прав для этого действия.", ephemeral=True
            )
            return

        await interaction.response.defer()

        # Обновляем embed — зелёный
        async for msg in interaction.channel.history(limit=10):
            if msg.author == interaction.guild.me and msg.embeds:
                embed = msg.embeds[0]
                embed.color = 0x00FF00
                embed.add_field(name="Кого", value=self.applicant.mention, inline=True)
                embed.add_field(name="Принял", value=interaction.user.mention, inline=True)
                await msg.edit(embed=embed, view=None)
                break

        await send_log(
            guild=interaction.guild,
            applicant=self.applicant,
            status="accepted",
            reviewer=interaction.user,
            channel=interaction.channel,
        )

        await interaction.followup.send("✅ Заявка принята! Канал будет удалён через 5 секунд.")
        import asyncio
        await asyncio.sleep(5)
        await interaction.channel.delete(reason="Заявка принята")

    @discord.ui.button(
        label="Взять на рассмотрение",
        style=discord.ButtonStyle.primary,
        custom_id="app_review",
    )
    async def take_review(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_reviewer_role(interaction.user):
            await interaction.response.send_message(
                "❌ У вас нет прав для этого действия.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"🔍 {interaction.user.mention} взял(а) на рассмотрение вашу заявку, {self.applicant.mention}!"
        )
        button.disabled = True
        await interaction.message.edit(view=self)

    @discord.ui.button(
        label="Вызвать на обзвон",
        style=discord.ButtonStyle.primary,
        custom_id="app_call",
    )
    async def call_interview(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_reviewer_role(interaction.user):
            await interaction.response.send_message(
                "❌ У вас нет прав для этого действия.", ephemeral=True
            )
            return
        await interaction.response.send_modal(CallModal(applicant=self.applicant))

    @discord.ui.button(
        label="Отклонить",
        style=discord.ButtonStyle.danger,
        custom_id="app_reject",
    )
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_reviewer_role(interaction.user):
            await interaction.response.send_message(
                "❌ У вас нет прав для этого действия.", ephemeral=True
            )
            return
        await interaction.response.send_modal(
            RejectModal(applicant=self.applicant, ticket_channel=interaction.channel)
        )


# ──────────────────────────────────────────────
#  VIEW — дропдаун выбора категории заявки
# ──────────────────────────────────────────────
class ApplicationCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="za9vk1",
                description="Основная заявка",
                value="main_application",
            ),
        ]
        super().__init__(
            placeholder="Выберите категорию тикета",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="app_category_select",
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "main_application":
            await interaction.response.send_modal(ApplicationModal())


class ApplicationCategoryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ApplicationCategorySelect())


# ──────────────────────────────────────────────
#  Отправка логов
# ──────────────────────────────────────────────
async def send_log(
    guild: discord.Guild,
    applicant: discord.Member,
    status: str,
    reviewer: discord.Member = None,
    reason: str = None,
    channel: discord.TextChannel = None,
):
    logs_channel = guild.get_channel(LOGS_CHANNEL_ID)
    if not logs_channel:
        return

    if status == "accepted":
        color = 0x00FF00
        title = "✅ Заявка принята"
    elif status == "rejected":
        color = 0xFF0000
        title = "❌ Заявка отклонена"
    else:
        color = 0xFFFF00
        title = "🔍 Заявка на рассмотрении"

    embed = discord.Embed(title=title, color=color, timestamp=datetime.utcnow())
    embed.add_field(name="Пользователь", value=applicant.mention, inline=True)
    embed.add_field(name="Username", value=applicant.name, inline=True)
    embed.add_field(name="ID", value=str(applicant.id), inline=True)

    if reviewer:
        label = "Принял" if status == "accepted" else "Отказал"
        embed.add_field(name=label, value=reviewer.mention, inline=True)

    if reason:
        embed.add_field(name="Причина отказа", value=reason, inline=False)

    if channel:
        embed.add_field(name="Канал", value=channel.name, inline=False)

    await logs_channel.send(embed=embed)


# ──────────────────────────────────────────────
#  COG
# ──────────────────────────────────────────────
class Applications(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_view(ApplicationCategoryView())
        bot.add_view(ApplicationActionView(applicant=None))  # persistent

    @app_commands.command(
        name="setup_applications",
        description="Отправить сообщение с выбором категории заявки",
    )
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    async def setup_applications(self, interaction: discord.Interaction):
        channel = interaction.guild.get_channel(APPLICATIONS_CHANNEL_ID)
        if not channel:
            await interaction.response.send_message(
                "❌ Канал для заявок не найден. Проверь APPLICATIONS_CHANNEL_ID в .env",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="Заявки",
            description="Выберите категорию ниже, чтобы открыть форму заявки.",
            color=0xFF69B4,
        )

        file = None
        if BANNER_PATH and os.path.exists(BANNER_PATH):
            file = discord.File(BANNER_PATH, filename="banner.png")
            embed.set_image(url="attachment://banner.png")

        view = ApplicationCategoryView()

        if file:
            await channel.send(file=file, embed=embed, view=view)
        else:
            await channel.send(embed=embed, view=view)

        await interaction.response.send_message(
            "✅ Сообщение с заявками отправлено!", ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Applications(bot))
