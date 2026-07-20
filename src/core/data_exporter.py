"""
数据导出模块
支持 CSV/JSON 格式导出解析结果
"""

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class ExportData:
    """导出数据项"""
    timestamp: str
    direction: str  # 'RX' or 'TX'
    protocol: str
    raw_hex: str
    fields: dict[str, Any]
    is_valid: bool
    error_msg: str = ""


class DataExporter:
    """数据导出器"""

    def __init__(self):
        self.data_buffer: list[ExportData] = []
        self.max_buffer_size = 10000  # 最大缓冲条数

    def add_record(self, timestamp: str, direction: str, protocol: str,
                   raw_data: bytes, fields: dict[str, Any],
                   is_valid: bool = True, error_msg: str = ""):
        """添加记录"""
        record = ExportData(
            timestamp=timestamp,
            direction=direction,
            protocol=protocol,
            raw_hex=' '.join(f'{b:02X}' for b in raw_data),
            fields=fields,
            is_valid=is_valid,
            error_msg=error_msg
        )

        self.data_buffer.append(record)

        # 限制缓冲大小
        if len(self.data_buffer) > self.max_buffer_size:
            self.data_buffer = self.data_buffer[-self.max_buffer_size:]

    def add_from_parsed_frame(self, frame, direction: str = 'RX'):
        """从解析帧添加记录"""
        self.add_record(
            timestamp=frame.timestamp,
            direction=direction,
            protocol=frame.protocol,
            raw_data=frame.raw_data,
            fields=frame.fields,
            is_valid=frame.is_valid,
            error_msg=frame.error_msg
        )

    def export_csv(self, filepath: str) -> bool:
        """导出为 CSV 格式"""
        try:
            if not self.data_buffer:
                return False

            # 收集所有字段名
            all_fields = set()
            for record in self.data_buffer:
                all_fields.update(record.fields.keys())

            field_names = sorted(all_fields)

            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # 写入表头
                header = ['时间戳', '方向', '协议', '原始数据(HEX)', '有效'] + field_names
                if any(r.error_msg for r in self.data_buffer):
                    header.append('错误信息')
                writer.writerow(header)

                # 写入数据
                for record in self.data_buffer:
                    row = [
                        record.timestamp,
                        record.direction,
                        record.protocol,
                        record.raw_hex,
                        '是' if record.is_valid else '否'
                    ]

                    # 添加字段值
                    for field in field_names:
                        value = record.fields.get(field, '')
                        row.append(str(value))

                    # 添加错误信息
                    if record.error_msg:
                        row.append(record.error_msg)

                    writer.writerow(row)

            return True
        except Exception as e:
            print(f"CSV 导出失败: {e}")
            return False

    def export_json(self, filepath: str) -> bool:
        """导出为 JSON 格式"""
        try:
            if not self.data_buffer:
                return False

            data = {
                'export_time': datetime.now().isoformat(),
                'record_count': len(self.data_buffer),
                'records': []
            }

            for record in self.data_buffer:
                record_dict = {
                    'timestamp': record.timestamp,
                    'direction': record.direction,
                    'protocol': record.protocol,
                    'raw_hex': record.raw_hex,
                    'is_valid': record.is_valid,
                    'fields': record.fields,
                }
                if record.error_msg:
                    record_dict['error_msg'] = record.error_msg
                data['records'].append(record_dict)

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            return True
        except Exception as e:
            print(f"JSON 导出失败: {e}")
            return False

    def export_text(self, filepath: str) -> bool:
        """导出为纯文本格式"""
        try:
            if not self.data_buffer:
                return False

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("串口调试助手 - 数据导出\n")
                f.write(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"记录数: {len(self.data_buffer)}\n")
                f.write("=" * 80 + "\n\n")

                for i, record in enumerate(self.data_buffer, 1):
                    f.write(f"[{i}] {record.timestamp}\n")
                    f.write(f"    方向: {record.direction}\n")
                    f.write(f"    协议: {record.protocol}\n")
                    f.write(f"    原始: {record.raw_hex}\n")
                    f.write(f"    有效: {'是' if record.is_valid else '否'}\n")

                    if record.fields:
                        f.write("    字段:\n")
                        for key, value in record.fields.items():
                            f.write(f"        {key}: {value}\n")

                    if record.error_msg:
                        f.write(f"    错误: {record.error_msg}\n")

                    f.write("\n")

            return True
        except Exception as e:
            print(f"文本导出失败: {e}")
            return False

    def clear(self):
        """清空缓冲"""
        self.data_buffer.clear()

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        if not self.data_buffer:
            return {'count': 0}

        protocols = {}
        directions = {'RX': 0, 'TX': 0}
        valid_count = 0

        for record in self.data_buffer:
            protocols[record.protocol] = protocols.get(record.protocol, 0) + 1
            directions[record.direction] = directions.get(record.direction, 0) + 1
            if record.is_valid:
                valid_count += 1

        return {
            'count': len(self.data_buffer),
            'protocols': protocols,
            'directions': directions,
            'valid_count': valid_count,
            'invalid_count': len(self.data_buffer) - valid_count,
        }
