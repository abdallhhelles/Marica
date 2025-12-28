"""
FILE: cogs/utility.py
USE: General helper functions, information, and interactive dialogue.
FEATURES: Flag-based translation, Polls, Reminders, and Marcia Manuals.
"""
import discord
from discord.ext import commands
import asyncio
import random
from googletrans import Translator
from assets import MARICA_LORE, INTEL_DATABASE

# Expanded Language Library
FLAG_LANG = {
    "🇺🇸": "en", "🇬🇧": "en", "🇦🇺": "en", "🇨🇦": "en",
    "🇫🇷": "fr", "🇪🇸": "es", "🇩🇪": "de", "🇮🇹": "it", "🇵🇹": "pt", "🇳🇱": "nl", "🇷🇺": "ru",
    "🇯🇵": "ja", "🇰🇷": "ko", "🇨🇳": "zh-cn", "🇻🇳": "vi", "🇹🇭": "th",
    "🇦🇪": "ar", "🇹🇷": "tr", "🇮🇳": "hi", "🇧🇷": "pt"
}

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.translator = Translator()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Translation Matrix: React with a flag to translate a message."""
        if str(payload.emoji) in FLAG_LANG:
            channel = self.bot.get_channel(payload.channel_id)
            msg = await channel.fetch_message(payload.message_id)
            
            if not msg.content: return 
            
            dest = FLAG_LANG[str(payload.emoji)]
            try:
                # Running in thread to prevent blocking the bot
                tr = await asyncio.to_thread(self.translator.translate, msg.content, dest=dest)
                await msg.reply(f"📡 **DECODED [{dest.upper()}]:**\n{tr.text}", mention_author=False)
            except Exception as e:
                print(f"Translation Error: {e}")

    @commands.command(name="commands", aliases=["help"])
    async def list_commands(self, ctx):
        """Displays all available commands categorized by module."""
        embed = discord.Embed(
            title="🛠️ Marcia OS | Command Directory",
            description="All systems functional. Use `!manual` for a guide on how to use me.",
            color=0x3498db
        )

        for cog_name, cog in self.bot.cogs.items():
            cmd_list = cog.get_commands()
            if not cmd_list: continue
                
            filtered_cmds = [f"`!{cmd.name}`" for cmd in cmd_list if not cmd.hidden]
            if filtered_cmds:
                embed.add_field(name=f"📦 {cog_name}", value=" ".join(filtered_cmds), inline=False)

        embed.set_footer(text=f"Marcia OS v3.0 | Sector: {ctx.guild.name}")
        await ctx.send(embed=embed)

    @commands.command()
    async def manual(self, ctx):
        """A quick-start guide for new users and admins."""
        embed = discord.Embed(title="📖 Marcia OS | Operations Manual", color=0xf1c40f)
        embed.add_field(
            name="🛰️ For Admins", 
            value="1. Use `!setup` to link channels.\n2. Use `!event` to schedule missions.\n3. Use `!setup_trade` to open the market.", 
            inline=False
        )
        embed.add_field(
            name="🎣 For Traders", 
            value="Interact with the buttons in the Trading Terminal to add fish you have (Spares) or fish you need (Find).", 
            inline=False
        )
        embed.add_field(
            name="🌍 For Everyone", 
            value="React to any message with a 🇺🇸 or 🇪🇸 (and more) flag to translate it instantly!", 
            inline=False
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def tips(self, ctx):
        """Random survival tips and bot tricks."""
        tips_list = [
            "You can use `!remindme 60 Prepare for War` and I will DM you in one hour.",
            "If the mission timers look wrong, ask an admin to check the `!setup offset`.",
            "The Trading Terminal is server-specific. You won't see fish from other servers here!",
            "Use `!intel [topic]` to search the survival database for game-specific info."
        ]
        await ctx.reply(f"💡 **TIP:** {random.choice(tips_list)}")

    @commands.command()
    async def status(self, ctx):
        """System diagnostic and latency check."""
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(title="📡 System Diagnostic", color=0x2ecc71)
        embed.add_field(name="Signal Latency", value=f"🟢 {latency}ms")
        embed.add_field(name="Databank", value="🔵 SQL Stable")
        embed.add_field(name="Uptime", value="🔄 Full Operational Capacity")
        await ctx.reply(embed=embed)

    @commands.command()
    async def intel(self, ctx, topic: str = None):
        """Query survival topics (e.g., !intel trucks)."""
        if not topic: 
            return await ctx.reply(f"Available Intel Topics: `{', '.join(INTEL_DATABASE.keys())}`")
        
        info = INTEL_DATABASE.get(topic.lower())
        if info: 
            embed = discord.Embed(title=f"📥 INTEL: {topic.upper()}", description=info, color=0x3498db)
            await ctx.send(embed=embed)
        else:
            await ctx.reply("❌ Topic not found in the archives.")

    @commands.command()
    async def poll(self, ctx, question: str, *options):
        """Create a poll. Usage: !poll \"Title\" Yes No Maybe"""
        if not options:
            msg = await ctx.send(embed=discord.Embed(title="🗳️ POLL", description=question, color=0x00ffcc))
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")
        else:
            if len(options) > 10: return await ctx.send("Limit 10.")
            reactions = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
            desc = "\n".join([f"{reactions[i]} {opt}" for i, opt in enumerate(options)])
            msg = await ctx.send(embed=discord.Embed(title=f"🗳️ {question}", description=desc, color=0x00ffcc))
            for i in range(len(options)): await msg.add_reaction(reactions[i])

    @commands.command()
    async def remindme(self, ctx, minutes: int, *, task: str):
        """Set a reminder. !remindme 10 Wake Up"""
        await ctx.reply(f"⏰ Affirmative. Reminder set for `{task}`.")
        await asyncio.sleep(minutes * 60)
        await ctx.author.send(f"🔔 **REMINDER:** {task}")

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int = 5):
        """Purge chat history."""
        await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"🧹 {amount} signals cleared.", delete_after=3)

async def setup(bot):
    await bot.add_cog(Utility(bot))