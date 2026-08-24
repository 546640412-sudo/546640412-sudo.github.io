# -*- coding: utf-8 -*-
"""GitHub Actions 同步脚本：读飞书多维表格 → 生成门户数据 + 二维码。

通过飞书自建应用（app_id/secret）读数据，运行在 GitHub Actions（海外，访问飞书稳定）。
输出（写入仓库根目录，由 workflow 提交）：
  - streamers.json   门户索引（主播码/昵称/手机号/微信号/平台/进货单）
  - merchants.json   商户档案
  - cards/qr-{code}-return.png  ②主播专属码（主播回传表单预填）
  - cards/qr-{code}-dk.png      ③商家码（档口回传表单预填）
"""
import os, json
from urllib.parse import quote

APP_ID = os.environ["FEISHU_APP_ID"]
APP_SECRET = os.environ["FEISHU_APP_SECRET"]
BASE_TOKEN = "Y4EibpCK8aM9HCstBwach717nte"
LEDGER_TABLE = "tblvh3hUiZc5bgCa"      # 主播码台账
DK_TABLE = "tbll1Bk6HqJAzyd6"         # 档口回传表
MERCHANT_TABLE = "tblciaiN4cnQE5gZ"   # 商户档案

RETURN_URL = "https://ckzusnk8h4.feishu.cn/share/base/shrcn5aOyKvtNAJdAPGGhPnZMKb"
DK_URL = "https://ckzusnk8h4.feishu.cn/share/base/shrcnnAdaOmoXjLM8PPIEtFMQce"
ENROLL_URL = "https://ckzusnk8h4.feishu.cn/share/base/shrcnMkKbTVQR56rIFAGPriKSjc"

import urllib.request


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def get(url, token):
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def get_token():
    d = post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
             {"app_id": APP_ID, "app_secret": APP_SECRET})
    return d["tenant_access_token"]


def read_table(token, table_id):
    items = []
    page_token = None
    while True:
        url = ("https://open.feishu.cn/open-apis/bitable/v1/apps/" + BASE_TOKEN
               + "/tables/" + table_id + "/records?page_size=500")
        if page_token:
            url += "&page_token=" + page_token
        r = get(url, token)
        data = r.get("data", {})
        items.extend(data.get("items", []))
        if data.get("has_more"):
            page_token = data.get("page_token")
        else:
            break
    return items


def val(v):
    if isinstance(v, list):
        return v[0] if v else ""
    return v if v else ""


def main():
    token = get_token()

    # 1) 主播码台账
    streamers = []
    for it in read_table(token, LEDGER_TABLE):
        f = it.get("fields", {})
        code = val(f.get("自动主播码", "")) or val(f.get("主播码", ""))
        if not code:
            continue
        streamers.append({
            "code": str(code),
            "name": str(val(f.get("昵称", ""))),
            "wechat": str(val(f.get("微信号", ""))),
            "phone": str(val(f.get("手机号", ""))),
            "platform": str(val(f.get("直播平台", ""))),
            "card": "",
            "orders": [],
        })

    # 2) 档口回传表归集进货单
    orders_by_code = {}
    for it in read_table(token, DK_TABLE):
        f = it.get("fields", {})
        code = str(val(f.get("主播码", "")))
        if not code:
            continue
        orders_by_code.setdefault(code, []).append({
            "date": str(val(f.get("直播日期", ""))),
            "discount": str(val(f.get("折扣比例", ""))),
            "method": str(val(f.get("回传方式", ""))),
            "note": str(val(f.get("备注", ""))),
        })
    for s in streamers:
        s["orders"] = orders_by_code.get(s["code"], [])

    with open("streamers.json", "w", encoding="utf-8") as fp:
        json.dump({"enroll_form_url": ENROLL_URL, "streamers": streamers},
                  fp, ensure_ascii=False, indent=2)

    # 3) 生成二维码 PNG
    import qrcode
    FIELD = quote("主播码")
    os.makedirs("cards", exist_ok=True)
    for s in streamers:
        code = s["code"]
        qrcode.make(RETURN_URL + "?prefill_" + FIELD + "=" + code).save(
            "cards/qr-%s-return.png" % code)
        qrcode.make(DK_URL + "?prefill_" + FIELD + "=" + code).save(
            "cards/qr-%s-dk.png" % code)

    # 4) 商户档案
    merchants = []
    for it in read_table(token, MERCHANT_TABLE):
        f = it.get("fields", {})
        if not f.get("商铺名称"):
            continue
        merchants.append({
            "name": str(val(f.get("商铺名称", ""))),
            "address": str(val(f.get("地址", ""))),
            "category": str(val(f.get("主营类目", ""))),
            "contact_name": str(val(f.get("对接人", ""))),
            "contact_phone": str(val(f.get("联系方式", ""))),
        })
    with open("merchants.json", "w", encoding="utf-8") as fp:
        json.dump({"merchants": merchants}, fp, ensure_ascii=False, indent=2)

    print("同步完成：主播 %d 人，二维码 %d 张，商户 %d 家"
          % (len(streamers), len(streamers) * 2, len(merchants)))


if __name__ == "__main__":
    main()
