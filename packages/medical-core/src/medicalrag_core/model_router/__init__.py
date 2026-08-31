"""模型路由域：Model Target、三态熔断与确定性路由服务（spec「Model Router」）。

CONTEXT 术语：Model Target = 已配置的模型 provider 与能力集；路由按能力与
优先级排序，时间/瞬态错误推进到下一候选，Redis 电路保护病态候选
（closed/open/half-open 三态）。领域层只定义确定性选择规则与电路状态机；
具体电路存储（Redis）由 infra 提供。
"""
