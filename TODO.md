# TODO
- [ ] [context.py] 在 build_runtime_system_prompt() 中新增 PLAN 模式感知段落（类似 fast_mode），告知 LLM 当前处于只读分析模式
- [ ] [runtime.py] 在 refresh_runtime_client() 中调用 build_runtime_system_prompt() 重建 system prompt，使模式切换后 LLM 立即感知新模式
- [ ] [runtime.py] 验证 refresh_runtime_client() 中 bundle 对象的必要属性（cwd、extra_skill_dirs、extra_plugin_roots、include_project_memory）在调用点可用
- [ ] [测试] 编写/验证测试用例：进入 plan 模式后 system prompt 包含 plan mode 提示，退出后不再包含
- [x] [context.py] 在 build_runtime_system_prompt() 中新增 PLAN 模式感知段落 — 已完成
- [x] [runtime.py] 在 refresh_runtime_client() 中重建 system prompt — 已完成
- [x] [runtime.py] 可用性验证 — RuntimeBundle 所有必要属性均已存在 — 已完成
- [x] [测试] 编写/验证测试用例 — 所有 prompt 相关测试通过，权限模式切换逻辑验证通过
