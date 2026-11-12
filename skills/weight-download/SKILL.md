---
name: weight-download
description: 下载 Hugging Face 模型权重，诊断空间、认证、DNS、TLS和代理，比较线路、断点续传并按固定revision校验完整性。适用于权重下载慢、失败、续传或下载完成验收，不负责启动模型服务。
---

# 权重下载与完整性验收

先确认仓库读取权限、固定 revision、目标目录、真实挂载和可用容量，以及已有下载进程。复用有效凭据，不读取私钥、不将 Token、密码、签名URL或含凭据的代理地址写入文档/日志。

完整流程见 [权重下载、PC代理与测速](references/weight-download.md)：先选网络路线，再调整并发；需要时才读取 PC Negotiate、多个SSH隧道或 aria2 分段续传章节。现有环境和服务保持原样，不为提速擅自停其他下载或删除权重。

## 工具

- [scripts/hf_weight_manifest.py](scripts/hf_weight_manifest.py)：固定commit与文件清单，大小检查和正式checksum验收分开。
- [scripts/windows_sspi_proxy.ps1](scripts/windows_sspi_proxy.ps1)：仅在Windows上游需要当前用户认证时使用。
- [scripts/tcp_proxy_pool.py](scripts/tcp_proxy_pool.py)：将连接分配到多个已建立的回环SSH代理；本身不下载权重。

## 验收

一个目标文件只允许一个下载器写入，保留有效续传片段和控制文件；切换路线前检查写进程和断点。稀疏逻辑大小不能当已下载字节；进度区分完成文件、活动片段和估算的保留断点。

用相邻正常下载区间的字节差计算持续速度和剩余时间，暂停区间不计为网速。下载成功需要固定清单的文件数、大小及checksum通过；退出0或目录大小不等于校验成功。

空间不足时先列出占用与可清理候选，按已获授权范围处理，不默认 prune 或删除他人文件。只有用户要求周期回报时才建立定时监控，记录生命周期并在完成后结束监控。
