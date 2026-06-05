import pygame
import random
import sys
import os
import ctypes

# ── 调试开关 ──────────────────────────────────────────────────────────────────
DEBUG = True

def log(msg):
    if DEBUG:
        print(f'[DBG] {msg}', flush=True)

# ── 常量 ──────────────────────────────────────────────────────────────────────
SCREEN_W, SCREEN_H = 480, 720
FPS = 60

SKY_TOP = (131, 188, 249)
SKY_BOT = (152, 169, 230)

GRAVITY       = 0.55
JUMP_SPEED    = -14.0
MOVE_SPEED    = 5.5
CLOUD_W       = 90
CLOUD_H       = 90
PLANK_W_MIN   = 80
PLANK_W_MAX   = 170
PLANK_H       = 30
PLANK_GAP_MIN = 85
PLANK_GAP_MAX = 140
PURPLE_CHANCE = 0.25

IMG_DIR     = r'I:\plane_game2\img'
TYPE_BEIGE  = 'beige'
TYPE_PURPLE = 'purple'

BTN_W, BTN_H = 160, 50
BTN_RADIUS   = 12

# ── 浮空实体定义表 ────────────────────────────────────────────────────────────
# score_delta > 0 = 奖励（加分）; score_delta < 0 = 惩罚（减分）
ENTITY_DEFS = {
    'pet_star_cloud': {
        'img_dir':      'pet_star_cloud',
        'frame_count':  4,
        'size':         70,
        'score_delta':  +100,
        'speed_min':    0.5,
        'speed_max':    1.5,
        'spawn_chance': 0.003,   # 每帧概率，约5秒一只
        'max_count':    2,
        'anim_speed':   8,       # 每N帧切一次动画帧
        'margin':       10,      # 碰撞框内缩
    },
    'monster1': {
        'img_dir':      'monster1',
        'frame_count':  6,
        'size':         75,
        'score_delta':  -50,
        'speed_min':    1.0,
        'speed_max':    2.5,
        'spawn_chance': 0.004,
        'max_count':    3,
        'anim_speed':   5,
        'margin':       12,
    },
}


# ── 工具 ──────────────────────────────────────────────────────────────────────
def load_img(path, w, h):
    img = pygame.image.load(path).convert_alpha()
    return pygame.transform.smoothscale(img, (w, h))


def make_gradient_bg():
    surf = pygame.Surface((SCREEN_W, SCREEN_H))
    for y in range(SCREEN_H):
        t = y / (SCREEN_H - 1)
        r = int(SKY_TOP[0] + (SKY_BOT[0] - SKY_TOP[0]) * t)
        g = int(SKY_TOP[1] + (SKY_BOT[1] - SKY_TOP[1]) * t)
        b = int(SKY_TOP[2] + (SKY_BOT[2] - SKY_TOP[2]) * t)
        pygame.draw.line(surf, (r, g, b), (0, y), (SCREEN_W, y))
    return surf


def draw_round_rect(surf, color, rect, radius):
    pygame.draw.rect(surf, color, rect, border_radius=radius)


# ── 浮空实体（pet / monster 统一基类） ────────────────────────────────────────
class FloatingEntity:
    def __init__(self, kind, frames, x, y, vx, size, score_delta, anim_speed, margin):
        self.kind        = kind
        self.frames      = frames
        self.x           = float(x)
        self.y           = float(y)
        self.vx          = vx
        self.size        = size
        self.score_delta = score_delta   # 正=加分, 负=减分
        self.anim_speed  = anim_speed
        self.margin      = margin
        self.frame_idx   = 0
        self.frame_timer = 0
        self.alive       = True

    def update(self):
        self.x += self.vx
        if self.x + self.size < 0 or self.x > SCREEN_W:
            self.alive = False
            return
        self.frame_timer += 1
        if self.frame_timer >= self.anim_speed:
            self.frame_timer = 0
            self.frame_idx = (self.frame_idx + 1) % len(self.frames)

    def draw(self, surf):
        surf.blit(self.frames[self.frame_idx], (int(self.x), int(self.y)))

    def rect(self):
        m = self.margin
        return pygame.Rect(int(self.x) + m, int(self.y) + m,
                           self.size - m * 2, self.size - m * 2)


# ── 碰撞弹出文字（+100 / -50） ────────────────────────────────────────────────
class ScorePopup:
    DURATION = 55  # 存活帧数

    def __init__(self, x, y, delta, font):
        self.x     = float(x)
        self.y     = float(y)
        self.delta = delta
        self.font  = font
        self.timer = 0
        self.color = (80, 255, 100) if delta > 0 else (255, 80, 80)
        self.text  = f'+{delta}' if delta > 0 else str(delta)

    def update(self):
        self.y     -= 1.4
        self.timer += 1

    @property
    def alive(self):
        return self.timer < self.DURATION

    def draw(self, surf):
        alpha = max(0, 255 - int(255 * self.timer / self.DURATION))
        s = self.font.render(self.text, True, self.color)
        s.set_alpha(alpha)
        surf.blit(s, (int(self.x) - s.get_width() // 2, int(self.y)))


# ── 主角 ──────────────────────────────────────────────────────────────────────
class Cloud:
    SCROLL_THRESHOLD = SCREEN_H * 0.38

    def __init__(self, imgs):
        self.imgs = imgs
        self.image = imgs['smile']
        self.x = float(SCREEN_W // 2 - CLOUD_W // 2)
        self.y = float(SCREEN_H - 160)
        self.vx = 0.0
        self.vy = 0.0
        self.going_up = False
        self.falling  = False

    def do_jump(self, boosted=False):
        spd = JUMP_SPEED * (2.0 if boosted else 1.0)
        self.vy = spd
        self.vx = 0.0
        self.going_up = True
        self.falling  = False
        self.image = self.imgs['happy'] if boosted else self.imgs['smile']

    def update(self, keys):
        if self.going_up:
            if keys[pygame.K_LEFT]:
                self.vx = max(self.vx - 1.2, -MOVE_SPEED)
            elif keys[pygame.K_RIGHT]:
                self.vx = min(self.vx + 1.2, MOVE_SPEED)
            else:
                self.vx *= 0.82

        self.x += self.vx

        if self.x > SCREEN_W:
            self.x = -CLOUD_W
        elif self.x + CLOUD_W < 0:
            self.x = SCREEN_W

        self.vy += GRAVITY
        self.y  += self.vy

        if self.vy >= 0 and self.going_up:
            self.going_up = False
            self.falling  = True
            self.image = self.imgs['surprise']

    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), CLOUD_W, CLOUD_H)


# ── 木板 ──────────────────────────────────────────────────────────────────────
class Plank:
    def __init__(self, x, y, ptype, w, src_imgs):
        self.x     = float(x)
        self.y     = float(y)
        self.type  = ptype
        self.w     = w
        self.image = pygame.transform.smoothscale(src_imgs[ptype], (w, PLANK_H))

    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), self.w, PLANK_H)


# ── 游戏主体 ──────────────────────────────────────────────────────────────────
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption('云朵向上跳100层')
        self.clock  = pygame.time.Clock()

        try:
            hwnd = pygame.display.get_wm_info()['window']
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.SetFocus(hwnd)
            log('窗口强制前置成功')
        except Exception as e:
            log(f'窗口前置失败: {e}')

        try:
            self.font_big   = pygame.font.SysFont('microsoftyahei', 30, bold=True)
            self.font_small = pygame.font.SysFont('microsoftyahei', 20)
            self.font_btn   = pygame.font.SysFont('microsoftyahei', 22, bold=True)
            self.font_popup = pygame.font.SysFont('microsoftyahei', 26, bold=True)
        except Exception:
            self.font_big   = pygame.font.Font(None, 36)
            self.font_small = pygame.font.Font(None, 24)
            self.font_btn   = pygame.font.Font(None, 28)
            self.font_popup = pygame.font.Font(None, 32)

        self._load_assets()

        self._over_overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        self._over_overlay.fill((0, 0, 0, 160))

        gap    = 20
        total  = BTN_W * 2 + gap
        left_x = (SCREEN_W - total) // 2
        btn_y  = SCREEN_H // 2 + 60
        self.btn_retry  = pygame.Rect(left_x,               btn_y, BTN_W, BTN_H)
        self.btn_submit = pygame.Rect(left_x + BTN_W + gap,  btn_y, BTN_W, BTN_H)

        self.reset()

    # ── 资源加载 ──────────────────────────────────────────────────────────────
    def _load_assets(self):
        tc = os.path.join(IMG_DIR, 'thunder_cloud')
        pl = os.path.join(IMG_DIR, 'plank')

        self.cloud_imgs = {
            'smile':    load_img(os.path.join(tc, 'thunder_cloud_smile.png'),    CLOUD_W, CLOUD_H),
            'happy':    load_img(os.path.join(tc, 'thunder_cloud_happy.png'),    CLOUD_W, CLOUD_H),
            'surprise': load_img(os.path.join(tc, 'thunder_cloud_surprise.png'), CLOUD_W, CLOUD_H),
            'angry':    load_img(os.path.join(tc, 'thunder_cloud_angry.png'),    CLOUD_W, CLOUD_H),
            'shy':      load_img(os.path.join(tc, 'thunder_cloud_shy.png'),      CLOUD_W, CLOUD_H),
            'fight':    load_img(os.path.join(tc, 'thunder_cloud_fight.png'),    CLOUD_W, CLOUD_H),
        }

        purple_path = os.path.join(pl, 'plank_purple.png')
        if not os.path.exists(purple_path):
            purple_path = os.path.join(pl, 'e25020e35571a32027123e80514d8158_16.png')

        self.plank_src = {
            TYPE_BEIGE:  pygame.image.load(os.path.join(pl, 'plank_beige.png')).convert_alpha(),
            TYPE_PURPLE: pygame.image.load(purple_path).convert_alpha(),
        }

        self.bg = make_gradient_bg()

        # 加载所有实体的动画帧
        self.entity_frames = {}
        for kind, cfg in ENTITY_DEFS.items():
            d = os.path.join(IMG_DIR, cfg['img_dir'])
            self.entity_frames[kind] = [
                load_img(os.path.join(d, f'{i}.png'), cfg['size'], cfg['size'])
                for i in range(1, cfg['frame_count'] + 1)
            ]
            log(f'加载 {kind} 共 {cfg["frame_count"]} 帧')

    # ── 重置 ──────────────────────────────────────────────────────────────────
    def reset(self):
        self.total_scroll = 0
        self.entity_bonus = 0   # 实体碰撞带来的加/减分累计
        self.game_over    = False

        self.cloud    = Cloud(self.cloud_imgs)
        self.planks   = []
        self.entities = []   # 所有浮空实体（pet + monster 统一管理）
        self.popups   = []   # 碰撞弹出文字

        ground_y = SCREEN_H - 130
        self._add_plank(SCREEN_W // 2 - 90, ground_y, TYPE_BEIGE, w=180)

        self.cloud.x = float(SCREEN_W // 2 - CLOUD_W // 2)
        self.cloud.y = float(ground_y - CLOUD_H)

        self._fill_planks_above(ground_y)
        self.cloud.do_jump(boosted=False)
        log('游戏重置完成')

    @property
    def score(self):
        """高度分 + 实体奖惩，最低为 0。"""
        return max(0, int(self.total_scroll / 8) + self.entity_bonus)

    # ── 木板生成 ──────────────────────────────────────────────────────────────
    def _add_plank(self, x, y, ptype, w=None):
        if w is None:
            w = random.randint(PLANK_W_MIN, PLANK_W_MAX)
        self.planks.append(Plank(x, y, ptype, w, self.plank_src))

    def _fill_planks_above(self, from_y):
        y = from_y - random.randint(PLANK_GAP_MIN, PLANK_GAP_MIN + 20)
        while y > -SCREEN_H * 0.5:
            ptype = TYPE_PURPLE if random.random() < PURPLE_CHANCE else TYPE_BEIGE
            w = random.randint(PLANK_W_MIN, PLANK_W_MAX)
            x = random.randint(0, max(0, SCREEN_W - w))
            self._add_plank(x, y, ptype, w)
            y -= random.randint(PLANK_GAP_MIN, PLANK_GAP_MAX)

    def _ensure_planks_above(self):
        if not self.planks:
            return
        top_y = min(p.y for p in self.planks)
        while top_y > -SCREEN_H * 0.3:
            gap   = random.randint(PLANK_GAP_MIN, PLANK_GAP_MAX)
            top_y -= gap
            ptype = TYPE_PURPLE if random.random() < PURPLE_CHANCE else TYPE_BEIGE
            w = random.randint(PLANK_W_MIN, PLANK_W_MAX)
            x = random.randint(0, max(0, SCREEN_W - w))
            self._add_plank(x, top_y, ptype, w)

    # ── 滚屏 ──────────────────────────────────────────────────────────────────
    def _scroll(self, dy):
        self.cloud.y += dy
        for p in self.planks:
            p.y += dy
        for e in self.entities:
            e.y += dy
        for pp in self.popups:
            pp.y += dy
        self.total_scroll += dy

    # ── 表情切换 ──────────────────────────────────────────────────────────────
    def _update_expression(self):
        c = self.cloud
        sc = self.score
        if c.falling:
            c.image = c.imgs['surprise']
        elif sc > 500:
            c.image = c.imgs['fight']
        elif sc > 200:
            c.image = c.imgs['happy']
        else:
            c.image = c.imgs['smile']

    # ── 主更新 ────────────────────────────────────────────────────────────────
    def update(self, keys):
        if self.game_over:
            return

        self.cloud.update(keys)

        if self.cloud.y < Cloud.SCROLL_THRESHOLD:
            dy = Cloud.SCROLL_THRESHOLD - self.cloud.y
            self._scroll(dy)
            self.cloud.y = Cloud.SCROLL_THRESHOLD

        self._ensure_planks_above()
        self.planks = [p for p in self.planks if p.y < SCREEN_H + 60]

        # 木板碰撞（仅下落阶段）
        if self.cloud.falling:
            c_rect        = self.cloud.rect()
            cloud_bottom  = self.cloud.y + CLOUD_H
            cloud_bottom_prev = cloud_bottom - self.cloud.vy

            for p in self.planks:
                pr = p.rect()
                if (c_rect.right > pr.left and c_rect.left < pr.right and
                        cloud_bottom_prev <= pr.top + 6 and
                        cloud_bottom >= pr.top):
                    self.cloud.y       = p.y - CLOUD_H
                    self.cloud.falling = False
                    boosted = (p.type == TYPE_PURPLE)
                    if boosted:
                        log(f'踩中紫楹木！跳跃翻倍 得分={self.score}')
                    self.cloud.do_jump(boosted=boosted)
                    break

        self._update_expression()

        # ── 浮空实体生成 ──────────────────────────────────────────────────────
        for kind, cfg in ENTITY_DEFS.items():
            count = sum(1 for e in self.entities if e.kind == kind)
            if count < cfg['max_count'] and random.random() < cfg['spawn_chance']:
                from_right = random.random() < 0.5
                vx   = random.uniform(cfg['speed_min'], cfg['speed_max'])
                size = cfg['size']
                if from_right:
                    px, vx = SCREEN_W, -vx
                else:
                    px = -size
                py = random.randint(int(SCREEN_H * 0.1), int(SCREEN_H * 0.75))
                self.entities.append(FloatingEntity(
                    kind, self.entity_frames[kind],
                    px, py, vx,
                    size, cfg['score_delta'], cfg['anim_speed'], cfg['margin']
                ))
                tag = '+奖励' if cfg['score_delta'] > 0 else '-惩罚'
                log(f'{kind}({tag}) 出现 x={px:.0f} vx={vx:.2f}')

        # ── 实体更新 + 碰撞 ───────────────────────────────────────────────────
        c_rect = self.cloud.rect()
        for e in self.entities:
            e.update()
            if e.alive and c_rect.colliderect(e.rect()):
                e.alive = False
                self.entity_bonus += e.score_delta
                cx = int(e.x + e.size / 2)
                cy = int(e.y)
                self.popups.append(ScorePopup(cx, cy, e.score_delta, self.font_popup))
                sign = '+' if e.score_delta > 0 else ''
                log(f'碰到 {e.kind}！{sign}{e.score_delta}分 当前总分={self.score}')

        self.entities = [e for e in self.entities if e.alive]

        # 弹出文字更新
        for pp in self.popups:
            pp.update()
        self.popups = [pp for pp in self.popups if pp.alive]

        # 坠落游戏结束
        if self.cloud.y > SCREEN_H + 40:
            self.game_over = True
            self.cloud.image = self.cloud_imgs['angry']
            log(f'游戏结束 得分={self.score}')

    # ── 渲染 ──────────────────────────────────────────────────────────────────
    def draw(self, mouse_pos):
        self.screen.blit(self.bg, (0, 0))

        for p in self.planks:
            self.screen.blit(p.image, (int(p.x), int(p.y)))

        for e in self.entities:
            e.draw(self.screen)

        self.screen.blit(self.cloud.image, (int(self.cloud.x), int(self.cloud.y)))

        for pp in self.popups:
            pp.draw(self.screen)

        self._draw_text_shadow(f'得分: {self.score}', self.font_big,
                               (255, 255, 255), (60, 80, 130), 12, 12)

        if self.game_over:
            self.screen.blit(self._over_overlay, (0, 0))
            cx = SCREEN_W // 2
            self._draw_centered('游戏结束！',        self.font_big, (255, 90, 90),   cx, SCREEN_H // 2 - 90)
            self._draw_centered(f'得分: {self.score}', self.font_big, (255, 255, 255), cx, SCREEN_H // 2 - 30)

            hover_r = self.btn_retry.collidepoint(mouse_pos)
            self._draw_btn(self.btn_retry,  '再玩一次',
                           (60, 180, 100) if hover_r else (40, 150, 80), (255, 255, 255))

            hover_s = self.btn_submit.collidepoint(mouse_pos)
            self._draw_btn(self.btn_submit, '提交成绩',
                           (100, 100, 180) if hover_s else (80, 80, 150), (220, 220, 255))

        pygame.display.flip()

    def _draw_btn(self, rect, text, bg_color, text_color):
        draw_round_rect(self.screen, bg_color, rect, BTN_RADIUS)
        surf = self.font_btn.render(text, True, text_color)
        self.screen.blit(surf, (rect.centerx - surf.get_width() // 2,
                                rect.centery - surf.get_height() // 2))

    def _draw_text_shadow(self, text, font, color, shadow_color, x, y):
        self.screen.blit(font.render(text, True, shadow_color), (x + 2, y + 2))
        self.screen.blit(font.render(text, True, color),        (x,     y))

    def _draw_centered(self, text, font, color, cx, y):
        surf = font.render(text, True, color)
        self.screen.blit(surf, (cx - surf.get_width() // 2, y))

    # ── 主循环 ────────────────────────────────────────────────────────────────
    def run(self):
        prev_left = prev_right = False

        while True:
            mouse_pos = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit(); sys.exit()

                if event.type == pygame.ACTIVEEVENT:
                    if event.state & 2:
                        log(f'键盘焦点: {"获得" if event.gain else "失去"}')
                    if event.state & 1:
                        log(f'鼠标焦点: {"获得" if event.gain else "失去"}')

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        pygame.quit(); sys.exit()
                    if event.key == pygame.K_r and self.game_over:
                        log('R键 重新开始')
                        self.reset()

                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self.game_over:
                        if self.btn_retry.collidepoint(event.pos):
                            log('点击「再玩一次」')
                            self.reset()
                        elif self.btn_submit.collidepoint(event.pos):
                            log('点击「提交成绩」（待实现）')

            keys = pygame.key.get_pressed()
            if DEBUG:
                if keys[pygame.K_LEFT]  and not prev_left:  log('左方向键 按下')
                if not keys[pygame.K_LEFT]  and prev_left:  log('左方向键 释放')
                if keys[pygame.K_RIGHT] and not prev_right: log('右方向键 按下')
                if not keys[pygame.K_RIGHT] and prev_right: log('右方向键 释放')
            prev_left  = bool(keys[pygame.K_LEFT])
            prev_right = bool(keys[pygame.K_RIGHT])

            self.update(keys)
            self.draw(mouse_pos)
            self.clock.tick(FPS)


if __name__ == '__main__':
    Game().run()
