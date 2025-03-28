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
        super().__init__(context)
        self.config = config  # 解析后的插件配置对象
        self.data_dir = os.path.join(os.path.dirname(__file__), "data")

        # 读取 CSV
        self.players_data = []
        self._load_players_csv()

        # 维护进行中的游戏：user_key -> { "target":..., "attempts":..., "max_attempts":... }
        self.sessions = {}

        # 可选：如果你想定时清理游戏会话，放置无限累积
        # asyncio.create_task(self._cleanup_task())

    def _load_players_csv(self):
        csv_path = os.path.join(self.data_dir, "players.csv")
        if not os.path.exists(csv_path):
            logger.warning(f"[CSGuessPlugin] players.csv not found: {csv_path}")
            return

        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.players_data.append(row)
            logger.info(f"[CSGuessPlugin] players.csv loaded: total = {len(self.players_data)} players.")
        except Exception as e:
            logger.error(f"[CSGuessPlugin] Failed to load CSV: {e}")

    async def _cleanup_task(self):
        while True:
            await asyncio.sleep(3600)
            self.sessions.clear()
            logger.info("[CSGuessPlugin] sessions cleared by _cleanup_task.")

    def _start_game_for_user(self, user_key: str):
        if not self.players_data:
            return None

        target = random.choice(self.players_data)
        # 从配置中获取最大猜测次数
        max_attempts = self.config.get("max_attempts", 6)
        self.sessions[user_key] = {
            "target": target,
            "attempts": 0,
            "max_attempts": max_attempts
        }
        return target

    def _end_game_for_user(self, user_key: str):
        if user_key in self.sessions:
            del self.sessions[user_key]

    @filter.command_group("csguess")
    def csguess_cmd_group(self):
        """
        指令组: /csguess ...
        包含子指令: start, guess, quit
        """
        pass

    @csguess_cmd_group.command("start")
    async def csguess_start(self, event: AstrMessageEvent):
        """
        /csguess start
        启动一个新的游戏。
        """
        user_key = event.unified_msg_origin
        target = self._start_game_for_user(user_key)
        if target is None:
            yield event.plain_result("选手数据为空，无法开始游戏。")
            return

        max_attempts = self.sessions[user_key]["max_attempts"]
        yield event.plain_result(
            f"新的猜选手游戏已开始！最大猜测次数：{max_attempts}。\n"
            "请使用 /csguess guess <NAME> 来进行猜测。\n"
            "若要放弃，请 /csguess quit。"
        )


    @csguess_cmd_group.command("guess")
    async def csguess_guess(self, event: AstrMessageEvent, guessed_name: str = None):
        """
        /csguess guess <NAME>
        猜测选手
        """
        user_key = event.unified_msg_origin
        session = self.sessions.get(user_key)
        if not session:
            yield event.plain_result("还没有开始游戏，请先 /csguess start。")
            return

        if not guessed_name:
            yield event.plain_result("请在指令后输入你猜的选手名，例如：/csguess guess S1mple")
            return

        # 取出目标
        target_player = session["target"]
        session["attempts"] += 1
        attempts_used = session["attempts"]
        attempts_left = session["max_attempts"] - attempts_used

        # CSV 查找
        guessed_player = None
        for p in self.players_data:
            if p.get("NAME", "").lower() == guessed_name.lower():
                guessed_player = p
                break

        if not guessed_player:
            yield event.plain_result(
                f"未找到 [{guessed_name}]，检查拼写。\n"
                f"已猜: {attempts_used}/{session['max_attempts']}，剩 {attempts_left} 次。"
            )
            return

        # 是否猜中
        if guessed_player["NAME"].lower() == target_player["NAME"].lower():
            yield event.plain_result(
                f"恭喜你猜对了！目标选手：[{target_player['NAME']}] \n游戏结束！"
            )
            self._end_game_for_user(user_key)
            return

        # 给出提示
        chain = []
        chain.append(Comp.Plain(f"你的猜测：[{guessed_player['NAME']}]\n\n"))

        # TEAM
        if guessed_player.get("TEAM", "") == target_player.get("TEAM", ""):
            chain.append(Comp.Plain("TEAM: Correct!\n"))
        else:
            chain.append(Comp.Plain("TEAM: Wrong\n"))

        # NATIONALITY
        if guessed_player.get("NATIONALITY", "") == target_player.get("NATIONALITY", ""):
            chain.append(Comp.Plain("NATIONALITY: Correct!\n"))
        else:
            chain.append(Comp.Plain("NATIONALITY: Wrong\n"))

        # AGE: 比较年龄 = 当前年份 - 出生年份
        now_year = datetime.now().year
        def calc_age(birth_str: str):
            try:
                parts = birth_str.split("-")
                birth_year = int(parts[0])
                return now_year - birth_year
            except:
                return 0

        g_age = calc_age(guessed_player.get("AGE", ""))
        t_age = calc_age(target_player.get("AGE", ""))

        if g_age == t_age:
            chain.append(Comp.Plain("AGE: Same\n"))
        elif g_age > t_age:
            chain.append(Comp.Plain("AGE: Higher\n"))
        else:
            chain.append(Comp.Plain("AGE: Lower\n"))

        # MAJOR APPEARANCES
        def to_int(s: str):
            try:
                return int(s)
            except:
                return 0

        g_major = to_int(guessed_player.get("MAJOR APPEARANCES", "0"))
        t_major = to_int(target_player.get("MAJOR APPEARANCES", "0"))

        if g_major == t_major:
            chain.append(Comp.Plain("MAJOR APPEARANCES: Same\n"))
        elif g_major > t_major:
            chain.append(Comp.Plain("MAJOR APPEARANCES: Higher\n"))
        else:
            chain.append(Comp.Plain("MAJOR APPEARANCES: Lower\n"))

        chain.append(Comp.Plain(f"\n已用 {attempts_used}/{session['max_attempts']}，剩 {attempts_left} 次。\n"))

        # 判断是否用完
        if attempts_left <= 0:
            chain.append(Comp.Plain(
                f"很遗憾，你用完所有机会！目标是 [{target_player['NAME']}]."
            ))
            yield event.chain_result(chain)
            self._end_game_for_user(user_key)
            return

        chain.append(Comp.Plain("继续加油，可再次 /csguess guess <NAME>！\n"))
        yield event.chain_result(chain)

    @csguess_cmd_group.command("quit")
    async def csguess_quit(self, event: AstrMessageEvent):
        """
        /csguess quit
        放弃游戏
        """
        user_key = event.unified_msg_origin
        session = self.sessions.get(user_key)
        if session:
            self._end_game_for_user(user_key)
            yield event.plain_result("你已放弃本局游戏，可随时 /csguess start 再来~")
        else:
            yield event.plain_result("你当前没有进行中的游戏。")

    async def terminate(self):
        """
        插件被卸载/停用时的清理逻辑
        """
        logger.info("[CSGuessPlugin] Terminate called.")
        self.sessions.clear()
