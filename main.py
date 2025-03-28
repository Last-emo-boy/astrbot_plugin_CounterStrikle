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

FEEDBACK_TEMPLATE = r"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8"/>
    <title>CS 猜谜</title>
    <style>
        html, body {
            margin: 0;
            padding: 0;
            width: 1280px;
            height: 720px;
            font-family: "Microsoft YaHei", sans-serif;
        }
        body {
            /* 可以加一个渐变背景 */
            background: linear-gradient(135deg, #f0f0f0, #e2e2e2);
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .container {
            background-color: #fff;
            width: 80%;
            max-width: 900px;
            min-height: 500px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            padding: 30px;
            box-sizing: border-box;
        }
        .title {
            font-size: 28px;
            font-weight: bold;
            margin-bottom: 15px;
            text-align: center;
        }
        .section {
            margin-bottom: 10px;
            font-size: 18px;
            line-height: 1.4;
        }
        .correct {
            color: green;
            font-weight: bold;
        }
        .wrong {
            color: red;
            font-weight: bold;
        }
        .highlight {
            color: #333;
            font-weight: bold;
        }
        hr {
            margin: 20px 0;
            border: none;
            border-top: 1px solid #ccc;
        }
        .footer {
            margin-top: 15px;
            font-size: 16px;
            text-align: center;
            color: #666;
        }
    </style>
</head>
<body>
    <div class="container">

        <div class="title">CS 猜谜 - 第 {{ attempt_used }} / {{ max_attempts }} 次尝试</div>

        <div class="section">
            <strong>本次猜测选手：</strong>
            <span class="highlight">{{ guessed_name }}</span>
        </div>

        <div class="section">
            <strong>所属队伍：</strong> {{ guessed_team }}
            {% if team_correct %}
                <span class="correct">（正确）</span>
            {% else %}
                <span class="wrong">（错误）</span>
            {% endif %}
        </div>

        <div class="section">
            <strong>国籍：</strong> {{ guessed_nationality }}
            {% if nationality_correct %}
                <span class="correct">（正确）</span>
            {% else %}
                <span class="wrong">（错误）</span>
            {% endif %}
        </div>

        <div class="section">
            <strong>截至 2025 年的年龄：</strong> {{ guessed_age }}
            {% if age_compare == 'same' %}
                <span>（相同）</span>
            {% elif age_compare == 'higher' %}
                <span class="wrong">（更大）</span>
            {% else %}
                <span class="wrong">（更小）</span>
            {% endif %}
        </div>

        <div class="section">
            <strong>Major 参赛次数：</strong> {{ guessed_major }}
            {% if major_compare == 'same' %}
                <span>（相同）</span>
            {% elif major_compare == 'higher' %}
                <span class="wrong">（更多）</span>
            {% else %}
                <span class="wrong">（更少）</span>
            {% endif %}
        </div>

        <div class="section">
            <strong>剩余次数：</strong>
            <span class="highlight">{{ attempts_left }}</span>
        </div>

        <hr/>

        <div class="footer">
            如果想继续猜测，请输入命令：<strong>/csguess guess &lt;选手名&gt;</strong> 
        </div>

    </div>
</body>
</html>
"""


@register(
    "astrbot_plugin_CounterStrikle",
    "w33d",                 
    "CS Guess Game (Wordle-like)",
    "1.0.0",
    "https://github.com/Last-emo-boy/astrbot_plugin_CounterStrikle"
) 

class CSGuessPlugin(Star):
    # 如果你需从配置文件获取最大猜测次数，可以加第二个参数 config: AstrBotConfig
    # 并在 init 里: self.max_attempts = config.get("max_attempts", 6)
    # 这里示例写死 6 次
    def __init__(self, context: Context):
        super().__init__(context)

        self.data_dir = os.path.join(os.path.dirname(__file__), "data")
        self.players_data = []
        self._load_players_csv()

        # 存放当前进行中的游戏信息
        # user_key -> { "target":..., "attempts":..., "max_attempts":... }
        self.sessions = {}

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
            logger.info(f"[CSGuessPlugin] players.csv loaded, total = {len(self.players_data)} players.")
        except Exception as e:
            logger.error(f"[CSGuessPlugin] Failed to load CSV: {e}")

    def _start_game_for_user(self, user_key: str):
        if not self.players_data:
            return None
        target = random.choice(self.players_data)
        # 如果需要配置化可改成: max_attempts = self.config.get("max_attempts", 6)
        max_attempts = 6
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
          - start
          - guess <NAME>
          - quit
        """
        pass

    @csguess_cmd_group.command("start")
    async def csguess_start(self, event: AstrMessageEvent):
        """
        /csguess start
        开始新游戏
        """
        user_key = event.unified_msg_origin
        target = self._start_game_for_user(user_key)
        if target is None:
            yield event.plain_result("选手数据为空，无法开始游戏。")
            return

        max_attempts = self.sessions[user_key]["max_attempts"]
        yield event.plain_result(
            f"新的 CSGuess 游戏已开始，你有 {max_attempts} 次机会！\n"
            f"请使用 /csguess guess <NAME> 来猜测。\n"
            f"若要放弃，请 /csguess quit"
        )

    @csguess_cmd_group.command("guess")
    async def csguess_guess(self, event: AstrMessageEvent, guessed_name: str):
        """
        /csguess guess <NAME>
        进行猜测
        """
        user_key = event.unified_msg_origin
        session = self.sessions.get(user_key)
        if not session:
            yield event.plain_result("你还没有开始游戏，请先 /csguess start。")
            return

        session["attempts"] += 1
        attempts_used = session["attempts"]
        attempts_left = session["max_attempts"] - attempts_used

        target_player = session["target"]

        # 查找猜测的选手
        guessed_player = None
        for p in self.players_data:
            if p.get("NAME", "").lower() == guessed_name.lower():
                guessed_player = p
                break

        # 如果不存在
        if not guessed_player:
            msg = f"未找到 [{guessed_name}]，请检查拼写。\n" \
                  f"已用 {attempts_used}/{session['max_attempts']}，剩余 {attempts_left} 次。"
            yield event.plain_result(msg)
            return

        # 如果名字猜对
        if guessed_player["NAME"].lower() == target_player["NAME"].lower():
            # 用另一个模板做「恭喜成功」的图片
            html_win = await self.html_render(WIN_TEMPLATE, {
                "target_name": target_player["NAME"]
            })
            yield event.image_result(html_win)

            self._end_game_for_user(user_key)
            return

        # 否则，构建反馈
        # 1. TEAM
        guessed_team = guessed_player.get("TEAM", "")
        target_team = target_player.get("TEAM", "")
        team_correct = (guessed_team == target_team)

        # 2. NATIONALITY
        guessed_nat = guessed_player.get("NATIONALITY", "")
        target_nat = target_player.get("NATIONALITY", "")
        nationality_correct = (guessed_nat == target_nat)

        # 3. AGE - 以 2025 为准
        def calc_age_2025(birth_str: str):
            try:
                birth_year = int(birth_str.split("-")[0])
                return 2025 - birth_year
            except:
                return 0

        g_age = calc_age_2025(guessed_player.get("AGE", ""))
        t_age = calc_age_2025(target_player.get("AGE", ""))

        if g_age == t_age:
            age_compare = "same"
        elif g_age > t_age:
            age_compare = "higher"
        else:
            age_compare = "lower"

        # 4. MAJOR APPEARANCES
        def to_int(s):
            try:
                return int(s)
            except:
                return 0

        g_major = to_int(guessed_player.get("MAJOR APPEARANCES", "0"))
        t_major = to_int(target_player.get("MAJOR APPEARANCES", "0"))

        if g_major == t_major:
            major_compare = "same"
        elif g_major > t_major:
            major_compare = "higher"
        else:
            major_compare = "lower"

        # 用 Jinja HTML -> 图片
        html_feedback = await self.html_render(FEEDBACK_TEMPLATE, {
            "attempt_used": attempts_used,
            "max_attempts": session["max_attempts"],
            "attempts_left": attempts_left,

            "guessed_name": guessed_player.get("NAME", ""),
            "guessed_team": guessed_team,
            "team_correct": team_correct,

            "guessed_nationality": guessed_nat,
            "nationality_correct": nationality_correct,

            "guessed_age": g_age,
            "age_compare": age_compare,

            "guessed_major": g_major,
            "major_compare": major_compare
        })

        yield event.image_result(html_feedback)

        # 判断是否用完
        if attempts_left <= 0:
            # 用完则 Reveal 答案 + 结束
            yield event.plain_result(
                f"很遗憾，你用完所有次数！正确答案是 [{target_player['NAME']}]."
            )
            self._end_game_for_user(user_key)

    @csguess_cmd_group.command("quit")
    async def csguess_quit(self, event: AstrMessageEvent):
        """
        /csguess quit
        放弃游戏
        """
        user_key = event.unified_msg_origin
        if user_key in self.sessions:
            self._end_game_for_user(user_key)
            yield event.plain_result("你已放弃本局游戏。下次可用 /csguess start 再来~")
        else:
            yield event.plain_result("你当前没有进行中的游戏。")

    async def terminate(self):
        """
        插件卸载/停用时清理
        """
        logger.info("[CSGuessPlugin] Terminate called.")
        self.sessions.clear()
