#!/usr/bin/env python3
"""Offline, explicit-schema SP report analysis. No network or account operations."""
import argparse
import csv
import hashlib
import io
import json
import math
import re
import sys
import zipfile
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class InputError(ValueError):
    pass


METRICS = ("impressions", "clicks", "spend", "orders", "sales")
COUNTS = {"impressions", "clicks", "orders"}
TEXT = ("campaign_id", "campaign_name", "ad_group_id", "ad_group_name", "target_id",
        "target", "match_type", "search_term", "advertised_asin", "advertised_sku")
SCOPE = ("account_alias", "marketplace", "currency", "ad_product")
ALLOWED = set(METRICS + TEXT + SCOPE + ("date",))


def require(condition, message):
    if not condition:
        raise InputError(message)


def iso_date(value, label):
    try:
        require(isinstance(value, str), f"{label}: 需要 ISO 日期字符串")
        return date.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise InputError(f"{label}: 需要 YYYY-MM-DD 日期") from exc


def timestamp(value):
    try:
        require(isinstance(value, str), "generated_at: 缺少带时区的生成时刻")
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(result.tzinfo is not None, "generated_at: 必须包含时区")
        return result
    except (ValueError, TypeError) as exc:
        raise InputError("generated_at: 需要带时区的 ISO 时间") from exc


def numeric(value, mode, currency, label, integer=False):
    require(value is not None and str(value).strip() != "", f"{label}: 缺失数值，不能按零处理")
    require(not isinstance(value, bool), f"{label}: 布尔值不是数值")
    if isinstance(value, (int, float, Decimal)):
        result = Decimal(str(value))
    else:
        raw = str(value).strip()
        symbol = {"USD":"$", "CAD":"$", "AUD":"$", "EUR":"€", "GBP":"£", "JPY":"¥", "CNY":"¥"}.get(currency)
        if symbol and raw.startswith(symbol):
            raw = raw[len(symbol):].strip()
        if raw.startswith(currency + " "):
            raw = raw[len(currency):].strip()
        if mode == "decimal_dot":
            pattern = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
            normalized = raw.replace(",", "")
        else:
            pattern = r"(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?"
            normalized = raw.replace(".", "").replace(",", ".")
        require(re.fullmatch(pattern, raw) is not None, f"{label}: 数字格式无效或与 number_format 不符")
        try:
            result = Decimal(normalized)
        except InvalidOperation as exc:
            raise InputError(f"{label}: 非法数值") from exc
    require(result.is_finite() and result >= 0, f"{label}: 仅接受有限非负数；调整项需单独核实")
    if integer:
        require(result == result.to_integral_value(), f"{label}: 计数必须是整数，确认不是其他指标")
    return result


def read_table(path, spec):
    require(path.is_file(), f"输入文件不存在: {path}")
    # Standalone script and packaged module both enforce limits before parsing.
    if __package__:
        from .bounded import read_bounded
    else:
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from aee.bounded import read_bounded
    blob=read_bounded(path)
    header_row = spec.get("header_row", 1)
    require(isinstance(header_row, int) and not isinstance(header_row, bool) and header_row >= 1,
            "header_row 必须是正整数")
    require(header_row<=100,'header_row 超过100行限制')
    selected_sheet = None
    if path.suffix.lower() in (".csv", ".tsv", ".txt"):
        require(spec.get("sheet") is None, "文本报表不支持 sheet")
        text = blob.decode(spec.get("encoding", "utf-8-sig"))
        delimiter = spec.get("delimiter") or ("\t" if path.suffix.lower() == ".tsv" else ",")
        require(isinstance(delimiter, str) and len(delimiter) == 1, "delimiter 必须是单个字符")
        rows=[]
        for index,values in enumerate(csv.reader(io.StringIO(text), delimiter=delimiter, strict=True),1):
            require(index<=header_row+100000,'报表超过10万行限制')
            require(len(values)<=256,'报表超过256列限制')
            rows.append((index,values))
    elif path.suffix.lower() == ".xlsx":
        try:
            import openpyxl
        except ImportError as exc:
            raise InputError("XLSX 需要 openpyxl；请使用已登记的捆绑 Python 或提供原始 CSV") from exc
        book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=False, keep_links=False)
        try:
            require(len(book.worksheets)<=32,'XLSX 超过32个工作表限制')
            require(all((s.max_row or 0)<=header_row+100000 and (s.max_column or 0)<=256 for s in book.worksheets),
                    'XLSX 工作表声明范围超过10万行或256列限制')
            # Some platform exports incorrectly declare dimension A1:A1.
            # Iterate actual XML rows; declared dimensions must not truncate facts.
            for candidate in book.worksheets:
                candidate.reset_dimensions()
            if spec.get("sheet"):
                require(spec["sheet"] in book.sheetnames, "指定的 sheet 不存在")
                sheet = book[spec["sheet"]]
            else:
                nonempty = [s for s in book if any(any(c.value is not None for c in row) for row in s.iter_rows())]
                require(len(nonempty) == 1, "XLSX 需要恰好一个非空工作表，或显式指定 sheet")
                sheet = nonempty[0]
            selected_sheet = sheet.title
            rows = []
            for index, cells in enumerate(sheet.iter_rows(), 1):
                require(index<=header_row+100000,'报表超过10万行限制')
                require(len(cells)<=256,'报表超过256列限制')
                require(not any(c.data_type == "f" for c in cells), f"XLSX 第 {index} 行含公式；请使用平台数值原始导出")
                rows.append((index, [c.value for c in cells]))
        finally:
            book.close()
    else:
        raise InputError("只支持 CSV/TSV/TXT/XLSX；不执行宏或自动转换其他格式")
    require(len(rows) >= header_row, "表头行不存在")
    headers = [str(v).strip() if v is not None else "" for v in rows[header_row-1][1]]
    while headers and not headers[-1]:
        headers.pop()
    require(headers and all(headers), "表头有空字段，先确认 header_row/导出格式")
    require(len(headers) == len(set(headers)), "存在重复表头，需明确选择字段")
    data = []
    for index, values in rows[header_row:]:
        if not any(v is not None and str(v).strip() for v in values):
            continue
        require(len(values) <= len(headers) or all(v is None or str(v).strip() == "" for v in values[len(headers):]),
                f"第 {index} 行列数超过表头，确认分隔符和额外字段")
        values = list(values[:len(headers)]) + [None] * max(0, len(headers)-len(values))
        data.append((index, dict(zip(headers, values))))
    return headers, data, selected_sheet


def inspect_file(path, spec):
    headers, rows, sheet = read_table(path, spec)
    return {"path":str(path), "sheet":sheet, "headers":headers, "data_rows":len(rows),
            "notice":"仅展示结构；尚未确认范围、字段或归因口径。"}


def validate_config(config, now=None):
    for field in ("account_alias", "marketplace", "currency", "timezone", "advertiser_type"):
        require(isinstance(config.get(field), str) and config[field].strip(), f"缺少业务元数据: {field}")
    require(config.get("ad_product") == "SP", "首版仅支持 SP；SB/SD 需另核口径")
    require(config["advertiser_type"] in ("seller", "vendor", "author"), "advertiser_type 需 seller/vendor/author")
    require(re.fullmatch(r"[A-Z]{3}", config["currency"]) is not None, "currency 需三字母大写代码")
    try:
        zone = ZoneInfo(config["timezone"])
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InputError("timezone 需有效 IANA 时区") from exc
    period = config.get("period")
    require(isinstance(period, dict), "缺少 period")
    start, end = iso_date(period.get("start"), "period.start"), iso_date(period.get("end"), "period.end")
    require(start <= end, "统计期开始晚于结束")
    window = config.get("attribution_window_days")
    require(isinstance(window, int) and not isinstance(window, bool) and 1 <= window <= 365,
            "需显式确认 attribution_window_days 正整数")
    lag = config.get("reporting_lag_hours")
    require(isinstance(lag, (int, float)) and not isinstance(lag, bool) and math.isfinite(lag) and 0 <= lag <= 720,
            "reporting_lag_hours 需明确的 0–720 小时缓冲假设")
    require(config.get("number_format") in ("decimal_dot", "decimal_comma"), "需明确 number_format")
    reports = config.get("reports")
    require(isinstance(reports, list) and len(reports) == 2 and all(isinstance(r,dict) for r in reports) and {r.get("type") for r in reports} == {"campaign", "search_term"},
            "需恰好一份 campaign 和一份 search_term，禁止叠加快照")
    times = [timestamp(r.get("generated_at")) for r in reports]
    require(all(t.astimezone(zone).date() >= end for t in times), "报表生成日期早于统计期结束")
    now = now or datetime.now(timezone.utc)
    require(all(t <= now + timedelta(minutes=5) for t in times),
            "generated_at 在未来，超过 5 分钟时钟容差；不能据此判断归因成熟")
    rules = config.get("rules", {})
    require(isinstance(rules, dict), "rules 必须为对象")
    require(set(rules) <= {"target_acos", "minimum_clicks", "minimum_orders", "zero_order_spend_limit"}, "存在未知规则字段")
    parsed = {}
    for field in ("target_acos", "minimum_clicks", "minimum_orders", "zero_order_spend_limit"):
        value = rules.get(field)
        if value is None:
            parsed[field] = None
        else:
            require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0,
                    f"{field} 必须为正数或 null")
            require(field not in ("minimum_clicks", "minimum_orders") or int(value) == value, f"{field} 必须为整数")
            parsed[field] = Decimal(str(value))
    return zone, start, end, window, lag, min(times), parsed


def empty_totals():
    return {m:Decimal(0) for m in METRICS}


def add(total, row):
    for field in METRICS:
        total[field] += row[field]


def metrics(total):
    result = {field:str(total[field]) for field in METRICS}
    for name, numerator, denominator in (("ctr","clicks","impressions"), ("cpc","spend","clicks"),
                                         ("cvr","orders","clicks"), ("acos","spend","sales"), ("roas","sales","spend")):
        result[name] = str(total[numerator]/total[denominator]) if total[denominator] else None
    return result


def read_report(spec, config, base, validated):
    zone, start, end, window, lag, asof, _ = validated
    allowed_spec = {"type", "path", "generated_at", "scope_confirmed", "granularity", "sheet", "header_row",
                    "date_format", "encoding", "delimiter", "extra_dimensions", "columns"}
    require(set(spec) <= allowed_spec, "报表配置有未知字段；币种、归因窗口等统一在顶层确认，不能忽略分表差异")
    require(spec.get("scope_confirmed") is True, f"{spec['type']}: 需确认原始文件的店铺/站点/币种/SP 范围")
    require(isinstance(spec.get("path"), str) and spec["path"].strip(), f"{spec['type']}: 缺少 path")
    path = (base / spec["path"]).resolve()
    headers, rows, sheet = read_table(path, spec)
    require(rows, f"{spec['type']}: 空报表，不把缺数据视为零表现")
    columns = spec.get("columns")
    require(isinstance(columns, dict), "columns 需要显式映射对象")
    require(set(columns) <= ALLOWED, "columns 包含未知规范字段，请将其他分组列放入 extra_dimensions")
    require(all(isinstance(v, str) and v in headers for v in columns.values()), "映射字段不在原始表头中")
    require(len(set(columns.values())) == len(columns), "一个原始字段不能映射为多个不同指标")
    required = set(METRICS) | {"campaign_id"}
    if spec["type"] == "search_term":
        required |= {"ad_group_id", "search_term"}
    granularity = spec.get("granularity")
    require(granularity in ("daily", "summary"), "granularity 需 daily 或 summary")
    if granularity == "daily":
        required.add("date")
    else:
        require("date" not in columns, "summary 不应映射 date；请选择正确粒度")
    require(required <= set(columns), f"缺少必需规范字段: {', '.join(sorted(required-set(columns)))}")
    extras = spec.get("extra_dimensions", [])
    require(isinstance(extras, list) and all(isinstance(x,str) and x in headers for x in extras), "extra_dimensions 列不存在")
    require(len(set(extras)) == len(extras) and not set(extras).intersection(columns.values()), "额外分组列重复")
    for field in ("orders", "sales"):
        detected = re.search(r"(\d+)\s*(?:day|天)", columns[field], re.I)
        require(not detected or int(detected.group(1)) == window, f"{field}: 原始列归因窗口与配置不一致")
        require(not re.search(r"promoted|halo|advertised\s+sku|other\s+sku|推广商品|其他商品", columns[field], re.I),
                f"{field}: 不能用 promoted/halo 子集替代总归因指标")
    mapped_rows, seen = [], set()
    for row_number, source in rows:
        record = {field:str(source[columns[field]]).strip() if source[columns[field]] is not None else "" for field in TEXT if field in columns}
        for field in required.intersection(TEXT):
            require(record.get(field), f"{spec['type']} 第 {row_number} 行缺少标识: {field}")
        for field in SCOPE:
            if field in columns:
                require(str(source[columns[field]]).strip() == config[field], f"第 {row_number} 行 {field} 与声明范围不符")
        if granularity == "daily":
            raw = source[columns["date"]]
            try:
                day = raw.date() if isinstance(raw, datetime) else raw if isinstance(raw, date) else datetime.strptime(str(raw).strip(), spec.get("date_format", "%Y-%m-%d")).date()
            except (ValueError, TypeError) as exc:
                raise InputError(f"第 {row_number} 行日期与 date_format 不符") from exc
            require(start <= day <= end, f"第 {row_number} 行日期超出声明期间")
        else:
            day = end
        record["date"] = day.isoformat() if granularity == "daily" else None
        record["extra_dimensions"] = {field:str(source[field]) if source[field] is not None else "" for field in extras}
        identity_fields = ("campaign_id",) if spec["type"] == "campaign" else ("campaign_id", "ad_group_id", "target_id", "target", "match_type", "search_term", "advertised_asin", "advertised_sku")
        key = (record["date"], *(record.get(field, "") for field in identity_fields), tuple(record["extra_dimensions"].items()))
        require(key not in seen, f"{spec['type']} 第 {row_number} 行粒度重复；检查重叠快照或遗漏分组列")
        seen.add(key)
        for field in METRICS:
            record[field] = numeric(source[columns[field]], config["number_format"], config["currency"],
                                    f"{spec['type']} 第 {row_number} 行 {field}", field in COUNTS)
        require(record["clicks"] <= record["impressions"], f"第 {row_number} 行点击大于曝光；需核对报表")
        require(record["clicks"] > 0 or record["spend"] == 0, f"第 {row_number} 行零点击有花费，需核对 SP/CPC 范围")
        require(record["orders"] > 0 or record["sales"] == 0,
                f"第 {row_number} 行订单为零但销售额大于零；先核对字段/归因口径")
        window_end = datetime.combine(day + timedelta(days=window+1), time.min, tzinfo=zone) + timedelta(hours=lag)
        record.update({"mature":window_end <= asof.astimezone(zone), "source_row":row_number,
                       "maturity_after":window_end.isoformat()})
        mapped_rows.append(record)
    observed_dates = sorted({r["date"] for r in mapped_rows if r["date"] is not None})
    info = {"type":spec["type"], "path":str(path), "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "size_bytes":path.stat().st_size, "sheet":sheet, "generated_at":spec["generated_at"],
            "columns":columns, "extra_dimensions":extras, "granularity":granularity,
            "row_count":len(mapped_rows), "scope_confirmed":True,
            "dates_with_records":observed_dates, "declared_days":(end-start).days+1,
            "scope_fields_verified_from_rows":[field for field in SCOPE if field in columns]}
    return mapped_rows, info


def choose_action(total, rules):
    clicks, orders, spend, sales = (total[x] for x in ("clicks", "orders", "spend", "sales"))
    if orders == 0 and sales > 0:
        return "observe", "订单与销售额矛盾，必须先核对字段/归因口径"
    if rules["minimum_clicks"] is None:
        return "observe", "未配置点击样本线"
    if clicks < rules["minimum_clicks"]:
        return "observe", "成熟点击不足已确认样本线"
    if orders == 0:
        limit = rules["zero_order_spend_limit"]
        if limit is not None and spend >= limit:
            return "review_negative", "成熟订单为零，点击与花费达到已确认阈值；待核相关性/匹配范围"
        return "observe", "零订单；花费线未配置或尚未达到"
    if rules["minimum_orders"] is None or orders < rules["minimum_orders"]:
        return "observe", "订单样本线未配置或成熟订单不足"
    if rules["target_acos"] is None or not sales:
        return "observe", "缺目标 ACOS 或无法计算 ACOS"
    acos = spend/sales
    if acos > rules["target_acos"]:
        return "review_reduce_bid", "成熟 ACOS 高于已确认目标；待核当前竞价/策略/商品利润"
    if acos < rules["target_acos"]:
        return "review_expansion", "成熟 ACOS 低于已确认目标；待核已有精准投放/库存/利润"
    return "maintain_review", "成熟 ACOS 等于目标；维持观察并人工复核"


def group_rows(rows, kind, rules):
    grouped = {}
    for row in rows:
        identity_fields = ("campaign_id",) if kind == "campaign" else ("campaign_id", "ad_group_id", "target_id", "target", "match_type", "search_term", "advertised_asin", "advertised_sku")
        key = tuple(row.get(field, "") for field in identity_fields) + (tuple(row["extra_dimensions"].items()),)
        if key not in grouped:
            grouped[key] = {"identity":{field:row[field] for field in TEXT if field in row},
                            "extra_dimensions":row["extra_dimensions"], "all":empty_totals(), "mature":empty_totals(),
                            "source_rows":[], "mature_source_rows":[], "observed_dates":[], "mature_dates":[]}
        group = grouped[key]
        add(group["all"], row)
        group["source_rows"].append(row["source_row"])
        if row["date"] is not None:
            group["observed_dates"].append(row["date"])
        if row["mature"]:
            add(group["mature"], row)
            group["mature_source_rows"].append(row["source_row"])
            if row["date"] is not None:
                group["mature_dates"].append(row["date"])
    output = []
    for group in grouped.values():
        group["observed_dates"] = sorted(set(group["observed_dates"]))
        group["mature_dates"] = sorted(set(group["mature_dates"]))
        if kind == "search_term":
            if group["mature_source_rows"]:
                group["action"], group["reason"] = choose_action(group["mature"], rules)
            else:
                group["action"], group["reason"] = "observe", "没有已成熟的归因日期"
        group["all"], group["mature"] = metrics(group["all"]), metrics(group["mature"])
        group["review_status"] = "pending_human_review"
        output.append(group)
    return sorted(output, key=lambda g:Decimal(g["all"]["spend"]), reverse=True)


def analyze(config_path):
    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    require(isinstance(config, dict), "配置根节点需为对象")
    validated = validate_config(config)
    rows_by_type, inputs = {}, []
    for spec in config["reports"]:
        rows, info = read_report(spec, config, config_path.parent, validated)
        rows_by_type[spec["type"]] = rows
        inputs.append(info)
    require(len({i["path"] for i in inputs}) == 2 and len({i["sha256"] for i in inputs}) == 2,
            "两种报表不能是同一文件或相同快照内容")
    campaign_ids = {r["campaign_id"] for r in rows_by_type["campaign"]}
    require({r["campaign_id"] for r in rows_by_type["search_term"]} <= campaign_ids,
            "搜索词存在未出现在活动报表的 campaign_id；先核对范围")
    totals = {}
    for kind, rows in rows_by_type.items():
        all_rows, mature_rows = empty_totals(), empty_totals()
        for row in rows:
            add(all_rows, row)
            if row["mature"]:
                add(mature_rows, row)
        totals[kind] = {"all":metrics(all_rows), "mature":metrics(mature_rows),
                        "rows":len(rows), "mature_rows":sum(r["mature"] for r in rows)}
    warnings = ["店铺/站点/广告类型等范围依赖用户确认；文件哈希只证明本次输入版本。",
                "候选仅供人工复核，不是后台批量上传文件；广告效率不等于利润或增量效果。",
                "当前版本仅经合成样本测试，真实店铺数据与业务阈值验证 pending。"]
    if inputs[0]["generated_at"] != inputs[1]["generated_at"]:
        warnings.append("两表生成时刻不同，可能存在快照变化；成熟截止采用较早时刻。")
    for source in inputs:
        if source["granularity"] == "daily" and len(source["dates_with_records"]) < source["declared_days"]:
            warnings.append(f"{source['type']} 声明期间 {source['declared_days']} 天，只有 {len(source['dates_with_records'])} 天有记录；其余日期可能无流量或未覆盖，不能自动认定为零。")
    for metric in METRICS:
        left = Decimal(totals["campaign"]["all"][metric])
        right = Decimal(totals["search_term"]["all"][metric])
        if left != right:
            warnings.append(f"两表 {metric} 覆盖不同：活动={left}，搜索词={right}；不相加、不强制抹平。")
    scope = {field:config[field] for field in ("account_alias", "marketplace", "currency", "timezone", "advertiser_type", "ad_product", "period", "attribution_window_days", "reporting_lag_hours")}
    return {"status":"computed_pending_business_review", "scope":scope, "business_goal":config.get("business_goal"),
            "maturity_as_of":validated[5].isoformat(), "rules":{k:str(v) if v is not None else None for k,v in validated[6].items()},
            "inputs":inputs, "totals":totals, "warnings":warnings,
            "campaigns":group_rows(rows_by_type["campaign"], "campaign", validated[6]),
            "search_terms":group_rows(rows_by_type["search_term"], "search_term", validated[6]),
            "row_maturity":{kind:[{key:r[key] for key in ("source_row", "date", "mature", "maturity_after")} for r in rows] for kind,rows in rows_by_type.items()}}


def csv_text(value):
    value = str(value)
    return "'"+value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def md(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def report_markdown(result):
    scope, totals = result["scope"], result["totals"]
    lines = ["# 亚马逊 SP 广告诊断计算底稿", "", "状态：计算完成，业务复核 pending。", "",
             f"范围：{md(scope['account_alias'])} / {md(scope['marketplace'])} / {scope['currency']} / {scope['timezone']}",
             f"期间：{scope['period']['start']} 至 {scope['period']['end']}；归因窗口 {scope['attribution_window_days']} 天。",
             f"成熟截止依据：{result['maturity_as_of']}；另含 {scope['reporting_lag_hours']} 小时分析缓冲假设。", "",
             "## 活动总体与搜索词覆盖", "", "| 范围 | 花费 | 归因销售额 | 归因订单 | ACOS | 成熟行/总行 |", "|---|---:|---:|---:|---:|---:|"]
    for kind, label in (("campaign","活动总体"),("search_term","搜索词细分")):
        t=totals[kind]
        acos=t["all"]["acos"]
        lines.append(f"| {label} | {t['all']['spend']} | {t['all']['sales']} | {t['all']['orders']} | {format(Decimal(acos)*100,'.2f')+'%' if acos is not None else 'N/A'} | {t['mature_rows']}/{t['rows']} |")
    lines += ["", "## 搜索词候选（按全期花费排序）", "", "全部对象见 candidates.csv，完整来源与阈值见 metrics.json。", "",
              "| 活动 ID | 搜索词/匹配对象 | 成熟花费 | 成熟订单 | 候选动作 | 原因 |", "|---|---|---:|---:|---|---|"]
    for item in result["search_terms"][:50]:
        identity=item["identity"]
        lines.append(f"| {md(identity['campaign_id'])} | {md(identity['search_term'])} | {item['mature']['spend']} | {item['mature']['orders']} | {item['action']} | {md(item['reason'])} |")
    lines += ["", "## 告警与待核实", ""] + ["- "+md(w) for w in result["warnings"]]
    lines += ["", "## 后续复核", "", "核实产品相关性、阶段、成本和库存，再检查当前竞价/预算/否定设置与期间变更。",
              "本底稿不判定最优竞价、预算受限、真实净利润或精确自然销量；未执行任何广告调整。", ""]
    return "\n".join(lines)


def write_outputs(result, output):
    output = Path(output).resolve()
    require(not output.exists(), "输出目录已存在；请指定新的运行目录，原结果不覆盖")
    # Called only after all input validation and computations succeed.
    output.mkdir(parents=True, exist_ok=False)
    (output/"metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n",encoding="utf-8")
    fields = list(TEXT) + ["period_start","period_end","observed_dates","mature_dates","currency","attribution_window_days","maturity_as_of",
              "all_clicks","all_spend","all_orders","all_sales","mature_clicks","mature_spend","mature_orders","mature_sales","mature_acos","action","reason","review_status",
              "source_file","source_rows","mature_source_rows","extra_dimensions","rules"]
    source = next(i["path"] for i in result["inputs"] if i["type"]=="search_term")
    with (output/"candidates.csv").open("w",encoding="utf-8-sig",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader()
        for item in result["search_terms"]:
            row = {field:item["identity"].get(field,"") for field in TEXT}
            for prefix in ("all","mature"):
                for metric in ("clicks","spend","orders","sales"):
                    row[prefix+"_"+metric]=item[prefix][metric]
            row.update({key:item[key] for key in ("action","reason","review_status")})
            row.update({"period_start":result["scope"]["period"]["start"],"period_end":result["scope"]["period"]["end"],
                        "observed_dates":json.dumps(item["observed_dates"]),"mature_dates":json.dumps(item["mature_dates"]),
                        "currency":result["scope"]["currency"],"attribution_window_days":result["scope"]["attribution_window_days"],
                        "maturity_as_of":result["maturity_as_of"]})
            row.update({"mature_acos":item["mature"]["acos"] or "N/A", "source_file":source,
                        "source_rows":json.dumps(item["source_rows"]), "mature_source_rows":json.dumps(item["mature_source_rows"]),
                        "extra_dimensions":json.dumps(item["extra_dimensions"],ensure_ascii=False),
                        "rules":json.dumps(result["rules"],ensure_ascii=False)})
            writer.writerow({key:csv_text(value) for key,value in row.items()})
    (output/"diagnosis.md").write_text(report_markdown(result),encoding="utf-8")


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    action=parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--inspect",type=Path)
    action.add_argument("--config",type=Path)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--sheet")
    parser.add_argument("--header-row",type=int,default=1)
    parser.add_argument("--encoding",default="utf-8-sig")
    parser.add_argument("--delimiter")
    args=parser.parse_args(argv)
    try:
        if args.inspect:
            require(args.output is None, "--inspect 不写输出目录")
            print(json.dumps(inspect_file(args.inspect.resolve(), {"sheet":args.sheet,"header_row":args.header_row,
                   "encoding":args.encoding,"delimiter":args.delimiter}),ensure_ascii=False,indent=2))
        else:
            require(args.output is not None, "分析需 --output 指定新的运行目录")
            result=analyze(args.config)
            require(not args.output.exists(), "输出目录已存在；原结果不覆盖")
            try:
                write_outputs(result,args.output)
            except OSError as exc:
                print(f"输出失败: {type(exc).__name__}；结果目录可能不完整，请检查后改用新目录。",file=sys.stderr)
                return 3
            print(json.dumps({"status":result["status"],"output":str(args.output.resolve()),
                              "search_term_groups":len(result["search_terms"])},ensure_ascii=False))
        return 0
    except (InputError, ValueError, OSError, csv.Error, KeyError, TypeError, zipfile.BadZipFile) as exc:
        print(f"输入校验失败: {exc}",file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
