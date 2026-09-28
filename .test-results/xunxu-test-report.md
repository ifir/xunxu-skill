# 循序（Xunxu）测试报告

- 时间：2026-09-28T11:44:05+08:00
- 结果：通过
- 总数：26
- 通过：26
- 失败：0
- 跳过：0
- 耗时：0.249 秒

## 用例

| 状态 | 用例 |
|---|---|
| passed | test_all_eleven_categories (__main__.ClassificationTests) |
| passed | test_ambiguous_and_special_code (__main__.ClassificationTests) |
| passed | test_distrust_uses_meaningful_name_as_targeted_hint (__main__.ConfigurationAndNamingTests) |
| passed | test_rename_format_and_group_limit (__main__.ConfigurationAndNamingTests) |
| passed | test_trust_name_policy (__main__.ConfigurationAndNamingTests) |
| passed | test_config_change_after_plan_rejected (__main__.ExecutionSafetyTests) |
| passed | test_destination_conflict_never_overwrites (__main__.ExecutionSafetyTests) |
| passed | test_existing_directory_switch (__main__.ExecutionSafetyTests) |
| passed | test_idempotent_second_plan (__main__.ExecutionSafetyTests) |
| passed | test_move_preserves_content_and_creates_outputs (__main__.ExecutionSafetyTests) |
| passed | test_source_change_after_plan_is_skipped (__main__.ExecutionSafetyTests) |
| passed | test_batch_analyzer_writes_evidence_not_body_to_stdout (__main__.PortabilityTests) |
| passed | test_document_text_and_docx_xml_extraction (__main__.PortabilityTests) |
| passed | test_fingerprint_survives_rename (__main__.PortabilityTests) |
| passed | test_generated_names_are_windows_safe (__main__.PortabilityTests) |
| passed | test_installer_is_non_overwriting_and_generic (__main__.PortabilityTests) |
| passed | test_xlsx_preview_is_bounded_and_includes_sheet_context (__main__.PortabilityTests) |
| passed | test_hidden_incomplete_symlink_and_recent (__main__.PrivacyAndTraversalTests) |
| passed | test_path_escape_rejected (__main__.PrivacyAndTraversalTests) |
| passed | test_private_file_filename_only_and_private_folder_pruned (__main__.PrivacyAndTraversalTests) |
| passed | test_failed_job_retries_then_stops (__main__.QueueTests) |
| passed | test_queue_checkpoint_merge_and_resume (__main__.QueueTests) |
| passed | test_stale_running_lease_is_recovered (__main__.QueueTests) |
| passed | test_installers_and_archives_never_request_analysis (__main__.ReportAndMediaTests) |
| passed | test_media_dependency_absence_is_safe_or_analyzer_returns_structure (__main__.ReportAndMediaTests) |
| passed | test_static_report_file_details (__main__.ReportAndMediaTests) |

## 边界说明

- 媒体测试默认验证安全降级；未安装 PaddleOCR/faster-whisper 时不会下载模型。
- 跨平台测试覆盖移动稳定指纹、文档解析和不覆盖式通用安装；真实 Windows 由 GitHub Actions 矩阵验证。
- 静态 HTML 测试覆盖文件详情弹窗、原始名称、当前名称、修改时间、大小和位置，不打开文件或文件夹。
- 对话自动触发与提问顺序需另做真实会话验收，Python 测试无法模拟产品路由。
