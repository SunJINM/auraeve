---
name: weather
description: 获取当前天气和预报（无需 API Key）。
homepage: https://wttr.in/:help
metadata: {"auraeve":{"emoji":"🌤️","requires":{"bins":["curl"]}}}
---

# 天气

两个免费服务，无需 API Key。

## wttr.in（主要）

快速单行命令：
```bash
curl -s "wttr.in/Beijing?format=3"
# 输出：Beijing: ⛅️ +15°C
```

紧凑格式：
```bash
curl -s "wttr.in/Beijing?format=%l:+%c+%t+%h+%w"
# 输出：Beijing: ⛅️ +15°C 60% ↙10km/h
```

完整预报：
```bash
curl -s "wttr.in/Beijing?T"
```

格式代码：`%c` 天气状况 · `%t` 温度 · `%h` 湿度 · `%w` 风速 · `%l` 位置 · `%m` 月相

提示：
- 空格 URL 编码：`wttr.in/New+York`
- 机场代码：`wttr.in/PEK`
- 单位：`?m`（公制）`?u`（英制）
- 仅今天：`?1` · 仅当前：`?0`
- PNG：`curl -s "wttr.in/Berlin.png" -o /tmp/weather.png`

## Open-Meteo（备用，JSON）

免费，无需 Key，适合程序化使用：
```bash
curl -s "https://api.open-meteo.com/v1/forecast?latitude=39.9&longitude=116.4&current_weather=true"
```

先查找城市坐标，再查询。返回含温度、风速、天气代码的 JSON。

文档：https://open-meteo.com/en/docs
