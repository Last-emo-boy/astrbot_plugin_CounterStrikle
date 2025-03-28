import os
import csv
import random
import asyncio
import astrbot.api.message_components as Comp

from datetime import datetime

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import AstrBotConfig

from astrbot.api import logger

@register(
    "astrbot_plugin_CounterStrikle",
    "w33d",                 
    "CS Guess Game (Wordle-like)",
    "1.0.0",
    "https://github.com/Last-emo-boy/astrbot_plugin_CounterStrikle"
)
class CSGuessPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        """
        config: AstrBot 在载入插件时，根据 _conf_schema.json 解析得到的配置对象。
        可以像 dict 一样使用，比如 self.config['max_attempts']。
        """
        super().__init__(context)
        self.config = config  # 保存到 self.config，后面要用

        # 插件自己的数据目录（跟随插件一起）
        self.data_dir = os.path.join(os.path.dirname(__file__), "data")
        self.players_data = []
        self._load_players_csv()

        # 用于记录用户会话状态:
        self.sessions = {}

        # 可选：如果想定期清理会话，防止积压，可以开个后台任务
        # asyncio.create_task(self._cleanup_task())

    def _load_players_csv(self):
        """
        加载 players.csv 并存储到 self.players_data（列表，每个元素是 dict）
        CSV 第一行示例:
         PAGE,NAME,REAL NAME,REGION,NATIONALITY,TEAM,AGE,WEAPON,MAJOR APPEARANCES,LAST UPDATED
        """
        csv_path = os.path.join(self.data_dir, "players.csv")
        if not os.path.exists(csv_path):
            self.context.logger.warning(f"[CSGuessPlugin] players.csv not found: {csv_path}")
            return
        
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.players_data.append(row)
            self.context.logger.info(f"[CSGuessPlugin] players.csv loaded: total = {len(self.players_data)} players.")
        except Exception as e:
            self.context.logger.error(f"[CSGuessPlugin] Failed to load CSV: {e}")

    async def _cleanup_task(self):
        """
        可选：定时清理过期的会话，防止 users 里的数据无限堆积。
        """
        while True:
            await asyncio.sleep(3600)
            self.sessions.clear()
            self.context.logger.info("[CSGuessPlugin] sessions cleared by _cleanup_task.")

    def _start_game_for_user(self, user_key: str):
        """
        为某个 user_key (可能是私聊ID，或群ID+用户ID等) 启动一个新的游戏。
        这里从 players_data 随机选取一个选手作为目标。
        """
        if not self.players_data:
            return None  # CSV没加载到数据

        target = random.choice(self.players_data)
        self.sessions[user_key] = {
            "target": target,
            "attempts": 0,
            # 最大猜测次数，从配置里拿
            "max_attempts": self.config.get("max_attempts", 6)
        }
        return target

    def _end_game_for_user(self, user_key: str):
        """
        结束并清理这个用户的游戏会话。
        """
        if user_key in self.sessions:
            del self.sessions[user_key]

    @filter.command_group("csguess")
    def csguess_cmd_group(self):
        """
        指令组: /csguess ...
        包含:
        1) /csguess start
        2) /csguess guess <Name>
        3) /csguess quit
        """
        pass

    @csguess_cmd_group.command("start")
    async def csguess_start(self, event: AstrMessageEvent):
        """
        /csguess start
        开始一个新游戏
        """
        user_key = event.unified_msg_origin
        target = self._start_game_for_user(user_key)
        if target is None:
            yield event.plain_result("抱歉，选手数据为空，无法开始游戏。")
            return

        max_attempts = self.sessions[user_key]["max_attempts"]
        yield event.plain_result(
            f"新的猜选手游戏已开始！\n"
            f"你有 {max_attempts} 次机会。\n"
            "请使用指令：/csguess guess <NAME> 来进行猜测。\n"
            "若要放弃，请 /csguess quit"
        )

    @csguess_cmd_group.command("guess")
    async def csguess_guess(self, event: AstrMessageEvent, guessed_name: str):
        """
        /csguess guess <NAME>
        用户猜测给定 NAME
        """
        user_key = event.unified_msg_origin
        session = self.sessions.get(user_key)

        # 1. 检查是否有进行中的游戏
        if not session:
            yield event.plain_result("你还没有开始游戏，请先使用 /csguess start 开始。")
            return
        
        target_player = session["target"]
        session["attempts"] += 1
        attempts_used = session["attempts"]
        attempts_left = session["max_attempts"] - attempts_used

        # 2. 找到 guessed_name 对应的选手信息
        guessed_player = None
        for p in self.players_data:
            if p.get("NAME", "").lower() == guessed_name.lower():
                guessed_player = p
                break
        
        if not guessed_player:
            yield event.plain_result(
                f"未在选手列表中找到 [{guessed_name}]，请确认拼写。\n"
                f"已用次数：{attempts_used} / {session['max_attempts']} (剩余 {attempts_left} 次)"
            )
            return
        
        # 3. 名字是否猜对
        if guessed_player["NAME"].lower() == target_player["NAME"].lower():
            yield event.plain_result(
                f"恭喜你猜对了！目标选手就是 [{target_player['NAME']}]!\n"
                "游戏结束~"
            )
            self._end_game_for_user(user_key)
            return
        
        # 4. 生成反馈
        feedback_chain = []
        feedback_chain.append(Comp.Plain(f"本次猜测：[{guessed_player['NAME']}]\n\n"))

        # TEAM (是否相同)
        if guessed_player.get("TEAM", "") == target_player.get("TEAM", ""):
            feedback_chain.append(Comp.Plain("TEAM: Correct!\n"))
        else:
            feedback_chain.append(Comp.Plain("TEAM: Wrong\n"))

        # NATIONALITY (是否相同)
        if guessed_player.get("NATIONALITY", "") == target_player.get("NATIONALITY", ""):
            feedback_chain.append(Comp.Plain("NATIONALITY: Correct!\n"))
        else:
            feedback_chain.append(Comp.Plain("NATIONALITY: Wrong\n"))

        # AGE: 比较「实际年龄」
        # 比如 "1994-07-01" => 2025 - 1994 = 31
        now_year = datetime.now().year  # 假设此处就是当前年份
        def to_age(birth_str: str) -> int:
            """
            返回「岁数」，若解析失败则返回 0
            仅通过 年份简单计算: now_year - birth_year
            """
            try:
                parts = birth_str.split("-")
                birth_year = int(parts[0])  # 假定第一段一定是年份
                return now_year - birth_year
            except:
                return 0
        
        guessed_age = to_age(guessed_player.get("AGE", ""))
        target_age = to_age(target_player.get("AGE", ""))

        if guessed_age == target_age:
            feedback_chain.append(Comp.Plain("AGE: Same\n"))
        elif guessed_age > target_age:
            feedback_chain.append(Comp.Plain("AGE: Higher\n"))
        else:
            feedback_chain.append(Comp.Plain("AGE: Lower\n"))

        # MAJOR APPEARANCES: higher/lower/same
        guessed_major_str = guessed_player.get("MAJOR APPEARANCES", "0")
        target_major_str = target_player.get("MAJOR APPEARANCES", "0")
        try:
            g_major = int(guessed_major_str)
        except:
            g_major = 0
        try:
            t_major = int(target_major_str)
        except:
            t_major = 0
        
        if g_major == t_major:
            feedback_chain.append(Comp.Plain("MAJOR APPEARANCES: Same\n"))
        elif g_major > t_major:
            feedback_chain.append(Comp.Plain("MAJOR APPEARANCES: Higher\n"))
        else:
            feedback_chain.append(Comp.Plain("MAJOR APPEARANCES: Lower\n"))
        
        feedback_chain.append(Comp.Plain(
            f"\n已用次数: {attempts_used} / {session['max_attempts']} (还剩 {attempts_left} 次)\n"
        ))
        
        # 如果次数用完，游戏失败
        if attempts_left <= 0:
            feedback_chain.append(Comp.Plain(
                f"很遗憾，你已经用完所有次数。\n"
                f"本局目标选手是 [{target_player['NAME']}].\n"
                "下次再接再厉！"
            ))
            yield event.chain_result(feedback_chain)
            self._end_game_for_user(user_key)
            return
        
        # 如果还没结束，就提示继续猜
        feedback_chain.append(Comp.Plain("继续加油，可再次使用 /csguess guess <NAME> 来猜。\n"))
        yield event.chain_result(feedback_chain)

    @csguess_cmd_group.command("quit")
    async def csguess_quit(self, event: AstrMessageEvent):
        """
        /csguess quit
        主动放弃当前游戏
        """
        user_key = event.unified_msg_origin
        session = self.sessions.get(user_key)
        if not session:
            yield event.plain_result("你当前并没有进行中的游戏。")
        else:
            self._end_game_for_user(user_key)
            yield event.plain_result("你已放弃本局游戏，可随时 /csguess start 再来一局~")

    async def terminate(self):
        """
        当插件被卸载/停用时的清理逻辑
        """
        self.context.logger.info("[CSGuessPlugin] Terminate called.")
        self.sessions.clear()
