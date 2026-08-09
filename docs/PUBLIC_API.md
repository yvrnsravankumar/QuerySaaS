# BI Publisher 0.3.2 Public API

```python
connection.get_folder_contents(folder_absolute_path="", item_type=None)
connection.download_bip_object(report_absolute_path, output_file=None, overwrite=False)
connection.upload_bip_object(report_object_absolute_path_url, object_type, object_zipped_data)
connection.extract_bip_object(object_zipped_data, output_directory=None, overwrite=False)
connection.get_bip_object_xml(report_absolute_path, member_name=None, include_non_xml=False)
connection.bip_object_exists(report_absolute_path)
connection.verify_bip_object(report_absolute_path, object_type=None, verification_mode="readable")
connection.delete_bip_object(report_absolute_path, *, missing_ok=False, verify=True, timeout=10, poll_interval=0.5)
connection.replace_bip_object(report_object_absolute_path_url, object_type, object_zipped_data, *, verify=True, timeout=10, poll_interval=0.5)
connection.plan_bip_object_copy(destination_connection, source_report_absolute_path, destination_absolute_path, object_type=None, overwrite=False)
connection.copy_bip_object(destination_connection, source_report_absolute_path, destination_absolute_path, object_type=None, *, overwrite=False, verify=True, dry_run=False)
connection.schedule_bip_report(report_absolute_path, *, output_format="csv", parameters=None, size_of_data_chunk_download=-1, notification_user_name=None, notification_to=None, notify_when_success=False, notify_when_failed=True, notify_when_skipped=False, notify_when_warning=True, save_data=True, save_output=True, schedule_public=True, job_name=None, user_job_desc=None)
```
