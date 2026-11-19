"""Loopback-only key entry. No telemetry, remote calls or credential receipts."""
import html
import http.server
import secrets
import sys
import socket
import threading
import time
import webbrowser
from urllib.parse import parse_qs
from .common import Error,require
from .research_mcp import PROVIDERS,configure,validate_key

STYLE='''body{background:#f5f1e6;color:#292d25;font:16px/1.7 system-ui;margin:0;padding:24px}main{max-width:680px;margin:auto;background:#fffdf7;border-top:5px solid #9c7d28;padding:28px;border-radius:8px}h1{font-size:26px}label{display:block;font-weight:600;margin-top:22px}input{display:block;width:100%;box-sizing:border-box;padding:14px;border:1px solid #aaa58f;border-radius:5px;font-size:16px;margin-top:8px}button{margin-top:24px;padding:14px 22px;background:#395d49;color:white;border:0;border-radius:5px;font-size:16px;cursor:pointer}small{color:#5e6558}a{color:#39634c}.note{padding:14px;background:#f1ead4}'''

class LocalKeyServer(http.server.HTTPServer):
    def handle_error(self,request,client_address):
        # Never print unexpected exception content from a credential request.
        print('Local key request failed; details suppressed.',file=sys.stderr)

class KeyHandler(http.server.BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        remaining=max(0,self.server.deadline-time.monotonic())
        self.connection.settimeout(max(.01,min(10,remaining)))
        def expire():
            try:self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        self.expiry_timer=threading.Timer(remaining,expire);self.expiry_timer.daemon=True;self.expiry_timer.start()
    def finish(self):
        try:super().finish()
        finally:self.expiry_timer.cancel()
    def log_message(self,*args):pass
    def host_ok(self):return self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}'
    def page(self,body,status=200):
        payload=('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>选品 MCP · 本地 Key 输入</title><style>'+STYLE+'</style><main>'+body+'</main></html>').encode('utf-8')
        self.send_response(status)
        for key,value in {'Content-Type':'text/html; charset=utf-8','Content-Length':str(len(payload)),'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'"}.items():self.send_header(key,value)
        self.end_headers();self.wfile.write(payload)
    def do_GET(self):
        if not self.host_ok() or self.path!='/':self.page('<h1>页面不存在</h1>',404);return
        if self.server.saved:self.page('<h1>配置已保存</h1>');return
        fields=[]
        for p in self.server.providers:
            spec=PROVIDERS[p]
            fields.append('<label for="'+p+'">'+html.escape(spec['name'])+' MCP Key</label><small><a target="_blank" rel="noreferrer" href="'+html.escape(spec['keys'],quote=True)+'">打开官方密钥管理</a></small><input id="'+p+'" name="'+p+'" type="password" required maxlength="4096" autocomplete="off">')
        self.page('<h1>选品 MCP · 本地 Key 输入</h1><p>填写自己的 MCP Key，不填写网页登录密码或完整连接URL。</p><p class="note">仅写入你选择的本机Codex私有配置（0600），保留原有设置及私有备份。表单不发送Key给作者、GitHub或店铺后台。</p><form method="post" action="/save" autocomplete="off"><input type="hidden" name="csrf" value="'+self.server.csrf+'">'+''.join(fields)+'<p>此入口只保存配置，不进行网络鉴权、业务取数或消费点数。保存后需刷新客户端，再按具体任务验证连接。</p><button type="submit">保存本机配置</button></form><p><small>请勿将Key发到聊天。关闭页面或到期未提交时不写入；可在终端按Ctrl+C停止。</small></p>')
    def do_POST(self):
        origin=f'http://127.0.0.1:{self.server.server_port}'
        if not self.host_ok() or self.path!='/save' or self.headers.get('Origin')!=origin:
            self.page('<h1>请求未获允许</h1>',403);return
        if time.monotonic()>=self.server.deadline:self.page('<h1>输入页面已到期，请重新启动</h1>',408);return
        if self.server.saved:self.page('<h1>已保存，请勿重复提交</h1>',409);return
        if self.headers.get('Content-Type','').split(';')[0]!='application/x-www-form-urlencoded':
            self.page('<h1>提交格式不支持</h1>',415);return
        try:
            length=int(self.headers.get('Content-Length','0'))
            require(0<length<=32768,'请求过大或缺少请求长度')
            raw=self.rfile.read(length)
            require(len(raw)==length,'请求不完整')
            form=parse_qs(raw.decode('utf-8'),keep_blank_values=True,max_num_fields=4)
            allowed={'csrf',*self.server.providers}
            require(set(form)==allowed and all(len(values)==1 for values in form.values()),'提交字段不完整或重复')
            if not secrets.compare_digest(form['csrf'][0],self.server.csrf):
                self.page('<h1>页面已失效，请重新打开本地入口</h1>',403);return
            keys=iter([validate_key(form[p][0]) for p in self.server.providers])
            if time.monotonic()>=self.server.deadline:self.page('<h1>输入页面已到期，未保存</h1>',408);return
            result=configure(self.server.provider,self.server.config,True,key_reader=lambda label:next(keys))
            self.server.saved=True;self.server.result=result
            form.clear()
            self.page('<h1>配置已保存在本机</h1><p>原配置已保留，文件权限为0600。本地输入服务现将关闭。</p><p>这还不表示已连接。请刷新或重开Codex对话，再按任务授权验证工具目录和小样本数据。没有修改店铺后台。</p>')
        except Error as exc:self.page('<h1>尚未完成保存</h1><p>'+html.escape(str(exc))+'</p><p><a href="/">返回重新填写</a></p>',409)
        except Exception:self.page('<h1>请求处理未完成</h1><p>没有输出密钥，请检查本地配置后重试。</p>',400)

def serve(provider,config,apply=False,open_browser=True,timeout=600):
    plan=configure(provider,config,False)
    require(10<=timeout<=3600,'本地输入页有效期须为10—3600秒')
    if not apply:return {**plan,'key_entry':'本机浏览器密码框；不接收聊天或命令参数中的Key','entry':'local_browser_password_form','bind':'127.0.0.1','expires_in_seconds':timeout,'start':'加 --apply 才启动，不接收真实Key参数'}
    require(sys.platform!='win32','本向导的私有配置写入目前仅验证POSIX；Windows见官方客户端说明')
    with LocalKeyServer(('127.0.0.1',0),KeyHandler) as server:
        server.csrf=secrets.token_urlsafe(32);server.provider=provider;server.providers=list(PROVIDERS) if provider=='both' else [provider]
        server.config=config;server.saved=False;server.result=None;server.timeout=.25;server.deadline=time.monotonic()+timeout
        url=f'http://127.0.0.1:{server.server_port}/'
        print('本地Key输入页：'+url,flush=True)
        if open_browser:
            try:webbrowser.open(url,new=2)
            except Exception:print('请自行打开上方本地地址。',flush=True)
        while not server.saved and time.monotonic()<server.deadline:server.handle_request()
        if server.saved:return server.result
        return {'status':'expired','config_saved':False,'network_calls':False,'shop_changes':False}
