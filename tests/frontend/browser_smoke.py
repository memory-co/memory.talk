"""Manual browser integration check using an isolated backend and temporary data."""
import json, os, shutil, socket, subprocess, tempfile, time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
with socket.socket() as listener:
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
base_url = f'http://127.0.0.1:{port}'
screenshots = Path(tempfile.mkdtemp(prefix='memorytalk-ui-screenshots-'))
with tempfile.TemporaryDirectory(prefix='mt-web-e2e-') as tmp:
    env = {**os.environ, 'MEMORY_TALK_HOME': tmp + '/home', 'MEMORY_TALK_WORKSPACE': tmp + '/workspace', 'MEMORY_TALK_TMUX_SOCKET': 'mt-web-' + Path(tmp).name}
    env.pop('MEMORY_TALK_TTYD_URL', None)
    with open(tmp + '/server.log', 'w') as log:
        server = subprocess.Popen(['python', '-m', 'uvicorn', 'memorytalk.backend.main:create_app', '--factory', '--host', '127.0.0.1', '--port', str(port)], cwd=ROOT, env=env, stdout=log, stderr=log)
        try:
            client = httpx.Client(base_url=base_url, timeout=15)
            for _ in range(60):
                try:
                    if client.get('/api/system/health').status_code == 200: break
                except httpx.ConnectError: pass
                if server.poll() is not None: raise RuntimeError(Path(tmp + '/server.log').read_text())
                time.sleep(.25)
            else: raise RuntimeError('Server not ready')
            def post(path, data):
                r = client.post('/api' + path, json=data)
                assert r.is_success, r.text
                return r.json()['data']
            post('/users', {'name':'alice', 'display_name':'Alice'})
            one = post('/works', {'goal':'让记忆成为下一次工作的起点'})
            two = post('/works', {'goal':'梳理项目的分层存储方案'})
            three = post('/works', {'goal':'为新的工作准备一些上下文'})
            post('/works', {'goal':'明确文件与认知层的边界', 'parent':two['id']})
            client.patch('/api/works/' + two['id'], json={'status':'doing'}).raise_for_status()
            post('/metas/card/memory.talk/把工作中的结论留下来', {'files': {'readme.md':'## 从一次工作到下一次开始\n\n工作会结束，但已经验证的认知可以被反复使用。\n\n- 用 **work** 组织正在做的事\n- 用 **issue** 留下问题与论证\n- 用 **card** 保存可以带走的结论\n\n> 每一次开始，都可以站在已有认知之上。', 'meta.yaml':'context: memory.talk 的认知闭环\nissue: memory.talk/如何留下可复用的认知\n'}})
            post('/metas/issue/memory.talk/如何留下可复用的认知', {'files': {'readme.md':'当一项工作完成时，哪些内容值得被下一项工作想起？', 'positions/把结论写成独立词条.md':'结论应当带着适用语境，能够独立读懂。\n\n## 论证\n- 下一次工作无需重新阅读全部工作单元。', 'meta.yaml':'summary: 优先保存经过验证且能够独立理解的结论。\npositions:\n  - claim: 把结论写成独立词条\n'}})
            errors=[]
            warnings=[]
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=os.environ.get('MEMORY_TALK_TEST_CHROMIUM') or shutil.which('chromium'), headless=True, args=['--no-sandbox','--disable-dev-shm-usage'])
                page=browser.new_page(viewport={'width':1440,'height':960}, device_scale_factor=1)
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('console', lambda message: warnings.append(message.text) if message.type == 'warning' else None)
                page.goto(base_url + '/', wait_until='networkidle')
                expect(page.get_by_role('heading', name='今天想做些什么？')).to_be_visible()
                page.screenshot(path=str(screenshots / 'home-desktop.png'), full_page=True, animations='disabled')
                page.get_by_role('textbox', name='工作目标').fill('浏览器验证：建立完整的工作流程')
                page.get_by_role('button', name='创建工作', exact=True).click()
                expect(page.get_by_role('heading', name='浏览器验证：建立完整的工作流程')).to_be_visible()
                page.get_by_role('combobox', name='工作状态', exact=True).click()
                page.get_by_role('option', name='进行中', exact=True).click()
                page.get_by_role('button', name='拆分工作').click()
                for _ in range(6):
                    page.keyboard.press('Tab')
                    assert page.evaluate("!!document.activeElement.closest('[role=dialog]')"), 'Dialog focus escaped'
                page.keyboard.press('Escape')
                expect(page.get_by_role('button', name='拆分工作')).to_be_focused()
                page.get_by_role('button', name='拆分工作').click()
                page.get_by_role('textbox', name='工作目标').fill('浏览器验证：子工作')
                page.get_by_role('button', name='创建工作', exact=True).click()
                expect(page.get_by_role('heading', name='浏览器验证：子工作')).to_be_visible()
                page.get_by_role('button', name='添加工作单元', exact=True).last.click()
                page.get_by_role('combobox', name='工作单元类型').click()
                page.get_by_role('option', name='终端', exact=True).click()
                page.get_by_role('button', name='打开工作单元', exact=True).click()
                expect(page.get_by_text('终端快照 · 只读')).to_be_visible(timeout=15000)
                # Destructive confirmation traps focus, cancels safely, and stays open on failure.
                end_button = page.get_by_role('button', name='结束并移除工作单元')
                end_button.click()
                expect(page.get_by_role('alertdialog')).to_be_visible()
                expect(page.get_by_role('button', name='保留工作单元')).to_be_focused()
                page.keyboard.press('Escape')
                expect(end_button).to_be_focused()
                end_button.click()
                page.route('**/worklets/*', lambda route: route.fulfill(status=503, content_type='application/json', body=json.dumps({'data':None,'message':'临时失败','error':'unavailable'})) if route.request.method == 'DELETE' else route.continue_())
                page.get_by_role('button', name='结束工作单元', exact=True).click()
                expect(page.get_by_role('alertdialog')).to_be_visible()
                expect(page.get_by_role('button', name='结束工作单元', exact=True)).to_be_enabled()
                page.get_by_role('button', name='保留工作单元').click()
                page.unroute('**/worklets/*')
                expect(end_button).to_be_focused()
                # Add a second real worklet and switch with the keyboard.
                page.get_by_role('button', name='添加工作单元', exact=True).click()
                page.get_by_role('button', name='打开工作单元', exact=True).click()
                tabs = page.get_by_role('tablist', name='工作单元切换')
                expect(tabs.get_by_role('tab')).to_have_count(2)
                tabs.get_by_role('tab').last.focus()
                page.keyboard.press('ArrowLeft')
                expect(tabs.get_by_role('tab').first).to_have_attribute('aria-selected', 'true')
                expect(page.get_by_text('终端快照 · 只读')).to_be_visible()
                page.get_by_role('button', name='打开认知库面板').click()
                page.get_by_role('button', name='把工作中的结论留下来').click()
                expect(page.get_by_role('heading', name='把工作中的结论留下来', exact=True)).to_be_visible()
                page.screenshot(path=str(screenshots / 'work-desktop.png'), full_page=True, animations='disabled')
                page.get_by_role('button', name='在主页面打开认知库').click()
                expect(page.get_by_role('heading', name='认知库', exact=True)).to_be_visible()
                page.get_by_role('button', name='编辑卡片').click()
                page.get_by_label('正文', exact=True).fill('## 已更新的结论\n\n浏览器保存的正文。')
                page.get_by_role('button', name='保存', exact=True).click()
                expect(page.get_by_role('heading', name='已更新的结论')).to_be_visible()
                # Updating content must preserve the existing discussion reference.
                page.get_by_role('button', name='查看这张卡片的讨论').click()
                expect(page.get_by_role('heading', name='立场与论证')).to_be_visible()
                expect(page.get_by_role('heading', name='把结论写成独立词条')).to_be_visible()
                page.screenshot(path=str(screenshots / 'library-desktop.png'), full_page=True, animations='disabled')
                page.get_by_role('tab', name='历史', exact=True).click()
                expect(page.locator('.history-list button').first).to_be_visible()
                page.locator('.history-list button').first.click()
                expect(page.get_by_text('历史版本', exact=False)).to_be_visible()
                page.get_by_role('button', name='回到当前版本').click()
                page.get_by_role('button', name='认知库', exact=True).first.click()
                page.get_by_role('button', name='新建卡片', exact=True).click()
                page.get_by_label('保存路径（最后一段为标题）').fill('测试/新卡片')
                page.get_by_label('正文', exact=True).fill('新建卡片内容')
                page.get_by_role('button', name='保存', exact=True).click()
                expect(page.get_by_role('heading', name='新卡片', exact=True)).to_be_visible()
                page.get_by_label('搜索认知库').fill('新建卡片内容')
                expect(page.locator('.catalog-item')).to_have_count(1)
                page.get_by_role('button', name='访客', exact=False).click()
                expect(page.get_by_role('heading', name='设置', exact=True)).to_be_visible()
                page.get_by_role('button', name='添加团队成员').click()
                page.get_by_label('用户名', exact=True).fill('browser_user')
                page.get_by_label('显示名称', exact=True).fill('浏览器用户')
                page.get_by_role('button', name='添加并使用', exact=True).click()
                expect(page.locator('[data-sidebar=footer] strong')).to_have_text('浏览器用户')
                page.get_by_role('button', name='新建工作', exact=False).first.click()
                expect(page.get_by_role('heading', name='浏览器用户，今天想做些什么？')).to_be_visible()
                page.reload(wait_until='networkidle')
                expect(page.get_by_role('heading', name='浏览器用户，今天想做些什么？')).to_be_visible()
                page.get_by_role('button', name='收起侧栏', exact=True).click()
                expect(page.get_by_role('button', name='展开侧栏')).to_be_visible()
                page.get_by_role('button', name='展开侧栏').click()
                page.keyboard.press('Control+k')
                page.get_by_role('combobox', name='搜索工作名称').fill('子工作')
                page.keyboard.press('ArrowDown')
                page.keyboard.press('Enter')
                expect(page.get_by_role('heading', name='浏览器验证：子工作')).to_be_visible()
                page.set_viewport_size({'width':390,'height':844})
                page.get_by_role('button', name='打开导航').click()
                expect(page.get_by_role('dialog', name='主导航')).to_be_visible()
                for _ in range(15):
                    page.keyboard.press('Tab')
                    assert page.evaluate("!!document.activeElement.closest('[role=dialog]')"), 'Sidebar focus escaped'
                page.keyboard.press('Escape')
                expect(page.get_by_role('button', name='打开导航')).to_be_focused()
                page.get_by_role('button', name='打开导航').click()
                page.get_by_role('button', name='新建工作', exact=False).first.click()
                expect(page.get_by_role('dialog', name='主导航')).not_to_be_visible()
                expect(page.get_by_role('heading', name='浏览器用户，今天想做些什么？')).to_be_visible()
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Horizontal overflow'
                page.screenshot(path=str(screenshots / 'home-mobile.png'), full_page=True, animations='disabled')
                page.set_viewport_size({'width':1440,'height':960})
                page.get_by_role('button', name='新建工作', exact=False).first.click()
                assert not warnings, warnings
                page.route('**/api/works', lambda route: route.fulfill(status=503, content_type='application/json', body=json.dumps({'data':None,'message':'测试：服务暂时不可用','error':'unavailable'})))
                page.reload(wait_until='networkidle')
                expect(page.get_by_role('alert').first).to_be_visible()
                assert not errors, errors
                browser.close()
            print('PASS: real API create/update work, nested work, bash worklet, library sidebar, card create/edit, metadata preservation, issue rendering, history, search, user registration, persisted identity, shortcuts, mobile navigation, error UI; dialog focus, keyboard tabs, mobile focus trap, failed destructive action; no browser runtime errors or accessibility warnings.')
            print(f'Screenshots: {screenshots}')
        finally:
            server.terminate()
            try: server.wait(timeout=10)
            except subprocess.TimeoutExpired: server.kill(); server.wait()
            if shutil.which('tmux'):
                subprocess.run(['tmux','-L',env['MEMORY_TALK_TMUX_SOCKET'],'kill-server'], capture_output=True)
