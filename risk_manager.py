

from math import isfinite
from datetime import datetime

class RiskManager:
    """
    PAPER 回测风控管理器。

    默认规则：
    - 回撤 >= 5%：WARNING
    - 回撤 >= 10%：暂停新开仓
    - 回撤 >= 15%：触发严重风险锁定
    - 严重风险锁定后，自动恢复不生效，必须人工确认
    - 平仓不受暂停开仓限制
    """

    def __init__(
        self,
        warning_drawdown=0.05,
        pause_drawdown=0.10,
        severe_drawdown=0.15,
        max_symbol_weight=0.30,
        max_total_weight=0.80,
        max_daily_trades=5,
        auto_resume=False,
        resume_cooldown_days=10,
    ):
        thresholds = [
            warning_drawdown,
            pause_drawdown,
            severe_drawdown,
        ]

        for value in thresholds:
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or not 0 < value < 1
            ):
                raise ValueError("回撤阈值必须是 0 到 1 之间的有限数值")

        if not (
            warning_drawdown < pause_drawdown < severe_drawdown
        ):
            raise ValueError("回撤阈值必须按预警、暂停、严重的顺序递增")

        for value in [max_symbol_weight, max_total_weight]:
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or not 0 < value <= 1
            ):
                raise ValueError("仓位上限必须大于 0 且不超过 1")

        if (
            isinstance(max_daily_trades, bool)
            or not isinstance(max_daily_trades, int)
            or max_daily_trades < 0
        ):
            raise ValueError("每日交易次数上限必须是非负整数")

        if not isinstance(auto_resume, bool):
            raise ValueError("auto_resume 必须是布尔值")

        if (
            isinstance(resume_cooldown_days, bool)
            or not isinstance(resume_cooldown_days, int)
            or resume_cooldown_days < 0
        ):
            raise ValueError("恢复冷却期必须是非负整数")

        self.warning_drawdown = float(warning_drawdown)
        self.pause_drawdown = float(pause_drawdown)
        self.severe_drawdown = float(severe_drawdown)

        self.max_symbol_weight = float(max_symbol_weight)
        self.max_total_weight = float(max_total_weight)
        self.max_daily_trades = max_daily_trades

        self.auto_resume = auto_resume
        self.resume_cooldown_days = resume_cooldown_days

        self.peak_equity = None
        self.current_equity = None
        self.current_drawdown = 0.0

        self.paused = False
        self.pause_reason = None
        self.paused_days = 0

        # 历史标记：是否曾经触发过严重回撤。
        # 人工恢复后保留该历史记录。
        self.severe_triggered = False

        # 当前锁定状态：严重回撤触发后，需要人工确认解除。
        self.severe_lock = False

        self.warning_triggered = False

        self.current_day = None
        self.daily_trades = 0

        self.events = []

    @staticmethod
    def _valid_positive_number(value):
        return (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and isfinite(value)
            and value > 0
        )

    @staticmethod
    def _valid_nonnegative_number(value):
        return (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and isfinite(value)
            and value >= 0
        )

    def _record_event(self, event_type, **details):
        event = {
            "type": event_type,
            "day": self.current_day,
        }
        event.update(details)
        self.events.append(event)

    def set_trading_day(self, day):
        """设置当前交易日；拒绝无效日期和倒序日期。"""
        if not isinstance(day, str):
            raise ValueError("交易日必须使用 YYYY-MM-DD 字符串")

        try:
            parsed_day = datetime.strptime(day, "%Y-%m-%d")
            if parsed_day.strftime("%Y-%m-%d") != day:
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError("交易日必须是有效的 YYYY-MM-DD 日期")

        if self.current_day is not None and day < self.current_day:
            raise ValueError("交易日不能早于当前交易日")

        if day == self.current_day:
            return

        self.current_day = day
        self.daily_trades = 0

        if self.paused:
            self.paused_days += 1

    def update_equity(self, equity, has_exposure=True):
        """
        更新账户权益、历史峰值、回撤和风险状态。

        has_exposure：账户当前是否持有风险仓位。
        空仓时权益不会再变化，回撤永远无法自行回落，
        因此自动恢复在空仓时不再要求回撤低于暂停阈值。
        """
        if not self._valid_positive_number(equity):
            raise ValueError("账户权益必须是有限正数")

        if not isinstance(has_exposure, bool):
            raise ValueError("has_exposure 必须是布尔值")

        equity = float(equity)
        self.current_equity = equity

        if self.peak_equity is None:
            self.peak_equity = equity
        else:
            self.peak_equity = max(self.peak_equity, equity)

        self.current_drawdown = (
            (self.peak_equity - equity) / self.peak_equity
        )

        drawdown = self.current_drawdown

        # 严重回撤是需要人工解除的活动锁定。
        if drawdown >= self.severe_drawdown:
            if not self.severe_triggered:
                self._record_event(
                    "SEVERE_DRAWDOWN",
                    drawdown=round(drawdown, 6),
                )
            elif not self.severe_lock:
                # 人工恢复后回撤仍超标，重新锁定并留痕。
                self._record_event(
                    "SEVERE_RELOCK",
                    drawdown=round(drawdown, 6),
                )

            self.severe_triggered = True
            self.severe_lock = True

        # 暂停新开仓。
        if drawdown >= self.pause_drawdown:
            if not self.paused:
                self.paused = True
                self.pause_reason = "DRAWDOWN_LIMIT"
                self.paused_days = 0

                self._record_event(
                    "TRADING_PAUSED",
                    drawdown=round(drawdown, 6),
                )

        # 预警只记录一次，避免每天重复生成相同事件。
        if (
            drawdown >= self.warning_drawdown
            and not self.warning_triggered
        ):
            self.warning_triggered = True

            self._record_event(
                "DRAWDOWN_WARNING",
                drawdown=round(drawdown, 6),
            )

        # 只有普通暂停可以自动恢复。
        # 严重回撤锁定必须通过人工确认解除。
        # 空仓时权益冻结、回撤无法回落：冷却期满后恢复，
        # 并把峰值重设为当前权益，避免永久暂停。
        if (
            self.paused
            and self.auto_resume
            and not self.severe_lock
            and self.paused_days >= self.resume_cooldown_days
            and (drawdown < self.pause_drawdown or not has_exposure)
        ):
            rebaselined = drawdown >= self.pause_drawdown

            if rebaselined:
                self.peak_equity = equity
                self.current_drawdown = 0.0
                drawdown = 0.0

            self.paused = False
            self.pause_reason = None
            self.paused_days = 0

            self._record_event(
                "AUTO_RESUME",
                drawdown=round(drawdown, 6),
                peak_rebaselined=rebaselined,
            )

        return {
            "equity": equity,
            "peak_equity": self.peak_equity,
            "drawdown": drawdown,
            "paused": self.paused,
            "severe_triggered": self.severe_triggered,
            "severe_lock": self.severe_lock,
        }

    def record_trade(self, day):
        """记录一笔已经成交的交易。"""
        if day != self.current_day:
            raise ValueError("交易日期与当前交易日不一致")

        self.daily_trades += 1

    def check_open(
        self,
        symbol,
        order_value,
        equity,
        positions_value,
    ):
        """检查新开仓是否符合风控限制。"""
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("股票代码不能为空")

        if not self._valid_positive_number(equity):
            raise ValueError("账户权益必须是有限正数")

        if not self._valid_positive_number(order_value):
            raise ValueError("开仓金额必须是有限正数")

        if not isinstance(positions_value, dict):
            raise ValueError("持仓市值必须是字典")

        for name, value in positions_value.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("持仓股票代码不能为空")

            if not self._valid_nonnegative_number(value):
                raise ValueError("持仓市值必须是有限非负数")

        reasons = []

        if self.paused:
            reasons.append("风控暂停开仓")

        if self.severe_lock:
            reasons.append("严重回撤锁定，必须人工确认恢复")

        # 人工恢复只清除标志，不改变当前回撤；
        # 回撤仍高于暂停阈值时不允许开仓。
        if (
            not self.paused
            and self.current_drawdown >= self.pause_drawdown
        ):
            reasons.append("当前回撤仍高于暂停阈值")

        if self.current_day is None:
            reasons.append("尚未设置当前交易日")

        if self.daily_trades >= self.max_daily_trades:
            reasons.append("超过每日交易次数上限")

        current_symbol_value = positions_value.get(symbol, 0.0)

        if (
            current_symbol_value + order_value
            > equity * self.max_symbol_weight + 1e-9
        ):
            reasons.append("超过单一标的仓位上限")

        total_position_value = sum(positions_value.values())

        if (
            total_position_value + order_value
            > equity * self.max_total_weight + 1e-9
        ):
            reasons.append("超过总持仓比例上限")

        return {
            "allowed": len(reasons) == 0,
            "reasons": reasons,
        }

    def resume_trading(self, confirm=False):
        """人工解除暂停；必须明确传入 confirm=True。"""
        if confirm is not True:
            raise ValueError("恢复交易必须明确传入 confirm=True")

        if not self.paused and not self.severe_lock:
            return self.get_status()

        was_severe_locked = self.severe_lock

        self.paused = False
        self.pause_reason = None
        self.paused_days = 0

        # 人工确认后解除当前严重锁定，但保留历史标记。
        self.severe_lock = False

        self._record_event(
            "MANUAL_RESUME",
            severe_lock_cleared=was_severe_locked,
            drawdown=round(self.current_drawdown, 6),
        )

        return self.get_status()

    def get_status(self):
        """返回当前风险状态及关键指标。"""
        if self.severe_lock:
            level = "SEVERE"
        elif (
            self.paused
            or self.current_drawdown >= self.pause_drawdown
        ):
            level = "PAUSED"
        elif self.current_drawdown >= self.warning_drawdown:
            level = "WARNING"
        else:
            level = "NORMAL"

        return {
            "level": level,
            "paused": self.paused,
            "pause_reason": self.pause_reason,
            "drawdown": round(self.current_drawdown, 6),
            "peak_equity": self.peak_equity,
            "current_equity": self.current_equity,
            "paused_days": self.paused_days,
            "daily_trades": self.daily_trades,
            "severe_triggered": self.severe_triggered,
            "severe_lock": self.severe_lock,
            "events": [event.copy() for event in self.events],
        }
