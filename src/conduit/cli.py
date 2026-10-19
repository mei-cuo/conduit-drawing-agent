# 命令行控制层：解析参数、读取配置、创建/恢复任务、返回退出码。
# 既可由 scripts/run.py 调用，也可由 python -m conduit 或测试调用。
# 退出码0表示导出完成，2表示等待人工复核，1表示运行异常；参数错误由 argparse 处理。
import argparse
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from .io import load_json, save_json
from .paths import CHECKPOINT_DIR, EXAMPLES_DIR, KNOWLEDGE_DIR, OUTPUT_DIR, PROJECT_ROOT


# 定义支持的参数及默认路径。--ocr 选择文字来源，--vision-backend 选择视觉观察来源。
# --mock 回放教学数据，--human-review 开启暂停复核，--resume 读取人工决策恢复原任务。
def parser():
    p = argparse.ArgumentParser(description="管井图纸识别：LangChain 模型组件 + LangGraph 工作流")
    # 输入与教学数据：真实输入为图片/PDF，mock则读取fixture中的预设OCR和观察。
    p.add_argument("--input", help="单页图片或多页 PDF")
    p.add_argument("--mock", action="store_true", help="回放预置观察，不进行真实识别")
    p.add_argument("--fixture", default=str(EXAMPLES_DIR / "demo_scene.json"))
    # 文字来源与视觉来源分别选择：例如sidecar OCR可以与真实模型API或文件观察配合。
    p.add_argument("--ocr", choices=["paddle", "paddle-http", "sidecar", "tesseract"], default="paddle-http")
    p.add_argument("--ocr-json")
    p.add_argument("--vision-backend", choices=["api", "agent-file"], default="api")
    p.add_argument("--agent-response", help="外部/子智能体完成的布局及观察响应 JSON")
    p.add_argument("--export-agent-request", action="store_true", help="完成预处理/OCR 后导出智能体请求，不调用视觉 API")
    p.add_argument("--out", help="默认保存至项目 outputs/run")
    p.add_argument("--knowledge-dir", default=str(KNOWLEDGE_DIR))
    # 识别范围与修复策略：严格名称范围见rules.py；模拟错误只用于演示和测试。
    p.add_argument("--strict-names", action="store_true")
    p.add_argument("--simulate-error", action="store_true", help="模拟首次提取引用错误，演示修复")
    p.add_argument("--max-repairs", type=int, default=1)
    # 复核与恢复：开启后仍有问题就暂停；恢复时要使用同一检查点和thread-id。
    p.add_argument("--human-review", action="store_true")
    p.add_argument("--thread-id")
    p.add_argument("--checkpoint", default=str(CHECKPOINT_DIR / "checkpoints.sqlite"))
    p.add_argument("--resume", help="包含 approve/reason/可选 observations 的人工决策 JSON")
    # 图像准备参数：DPI用于PDF渲染；tile-size和max-tiles控制视觉切片大小与数量。
    p.add_argument("--dpi", type=int, default=200)
    p.add_argument("--tile-size", type=int, default=1600)
    p.add_argument("--max-tiles", type=int, default=32)
    return p


# 统一运行入口，可传 argv 列表用于测试；未传时 argparse 读取终端参数。
# 步骤是读配置 → 校验参数 → 整理状态 → 导出外部请求或执行/恢复图 → 处理输出状态。
def main(argv=None):
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    # 从项目自身目录加载配置，避免终端切换到其他目录后读取错误的.env。
    load_dotenv(PROJECT_ROOT / ".env")
    # 日常结果与外部智能体交接材料使用不同默认目录，避免混在一起。
    if not args.out:
        args.out = str(OUTPUT_DIR / "agent-handoff" if args.export_agent_request
                       else OUTPUT_DIR / "run")
    # 先拒绝不完整或互相冲突的参数，避免启动模型/OCR后才发现任务无法执行。
    if args.resume and not args.thread_id:
        parser().error("--resume 需要原 --thread-id")
    if not args.resume and not args.mock and not args.input:
        parser().error("真实模式需要 --input；离线演示使用 --mock")
    if not args.resume and not args.mock and args.ocr == "sidecar" and not args.ocr_json:
        parser().error("sidecar 需要 --ocr-json")
    if not args.resume and not args.mock and args.vision_backend == "agent-file" and not args.agent_response and not args.export_agent_request:
        parser().error("agent-file 需要 --agent-response；或先 --export-agent-request")
    if args.export_agent_request and (args.mock or args.resume):
        parser().error("导出智能体请求只用于新的真实输入运行")
    if args.simulate_error and not args.mock:
        parser().error("--simulate-error 只能在 --mock 中使用")
    if not 0 <= args.max_repairs <= 3 or not 50 <= args.dpi <= 400 or args.tile_size <= 240 or args.max_tiles < 1:
        parser().error("max_repairs=0..3，dpi=50..400，tile_size>240，max_tiles>=1")
    # settings只保存业务参数；检查点路径、任务id和恢复入口由CLI管理。
    settings = vars(args).copy()
    for key in ("checkpoint", "thread_id", "resume"):
        settings.pop(key)
    # 把调用者传入的相对路径固定为绝对路径，便于稍后从另一个终端恢复任务。
    for key in ("input", "fixture", "ocr_json", "out", "knowledge_dir", "agent_response"):
        if settings.get(key):
            settings[key] = str(Path(settings[key]).resolve())
    state = {"workflow": "langgraph", "settings": settings}
    try:
        # 导出请求只需要预处理和OCR，完成后直接退出，不执行视觉识别和最终导出。
        if args.export_agent_request:
            from .agent_bridge import export_request
            export_request(state)
            return 0
        if not args.mock and args.vision_backend == "agent-file":
            # A saved response cannot autonomously call a live agent for another turn.
            # 文件后端无法自行获得新观察，禁止重复读取同一响应来冒充重新识别。
            settings["max_repairs"] = 0
        from .workflow import build_graph
        checkpoint = Path(args.checkpoint).resolve()
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        # 新任务默认生成唯一id；恢复必须使用原id。recursion_limit是图执行的额外上限。
        thread_id = args.thread_id or str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 40}
        print(f"thread_id={thread_id}; checkpoint={checkpoint}", file=sys.stderr)
        # 保存器随上下文关闭；同一检查点数据库中的多个任务用thread_id区分。
        with SqliteSaver.from_conn_string(str(checkpoint)) as saver:
            graph = build_graph(checkpointer=saver)
            existing = graph.get_state(config)
            # 恢复以检查点里的原始业务状态为准；Command只提交人工决策，不重建原任务输入。
            if args.resume:
                if not existing.next or not any(t.interrupts for t in existing.tasks):
                    raise ValueError("该 thread_id 没有待恢复的人工中断")
                payload = Command(resume=load_json(args.resume))
            else:
                # 已存在任务不允许当成新任务覆盖，防止旧复核材料意外丢失。
                if existing.values:
                    raise ValueError("thread_id 已存在；使用新 ID，或通过 --resume 恢复")
                payload = state
            result = graph.invoke(payload, config)
            # 暂停时先输出复核请求和恢复标识，最终results尚未生成，返回2让调用者识别该状态。
            if result.get("__interrupt__"):
                root = Path(result["settings"]["out"])
                save_json(root / "review_request.json", result["__interrupt__"][0].value)
                save_json(root / "run.json", {"thread_id": thread_id, "checkpoint": str(checkpoint),
                                               "status": "awaiting_review"})
                print(f"已暂停，待复核：{root / 'review_request.json'}", file=sys.stderr)
                return 2
        print(f"完成：{result['artifacts']['results']}", file=sys.stderr)
        return 0
    # 统一将运行异常变成退出码1，并保留错误类型；退出码0只表示导出成功。
    except Exception as exc:
        print(f"识别失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
