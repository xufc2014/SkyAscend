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
SCREEN_W, SCREEN_H = 600, 720
FPS = 60

SKY_TOP = (131, 188, 249)
SKY_BOT = (152, 169, 230)

GRAVITY          = 0.55
JUMP_SPEED       = -14.0
MOVE_SPEED       = 5.5
CLOUD_W          = 90
CLOUD_H          = 90
CLOUD_ANIM_SPEED = 10      # 主角动画切帧间隔

PLANK_W_MIN   = 80
PLANK_W_MAX   = 170
PLANK_H       = 30
PLANK_GAP_MIN = 110   # 最小间距
PLANK_GAP_MAX = 155   # 最大间距：严格小于最大跳高178px，留20px安全余量

# 单跳最大横向可达距离（上升25帧 × 5.5px/帧 = 140，留15px余量）
MAX_HORIZ_REACH = 125

# 木板类型
TYPE_BEIGE    = 'beige'    # 普通固定板
TYPE_PURPLE   = 'purple'   # 紫楹板：跳跃翻倍
TYPE_MOVING   = 'moving'   # 青蓝板：左右移动，出界销毁
TYPE_FRAGILE  = 'fragile'  # 玄棕板：站超1秒爆碎

PURPLE_CHANCE  = 0.10
FRAGILE_CHANCE = 0.12
# 移动板不参与随机概率池，只在横向太远时自动插入

MOVING_SPEED_MIN = 1.2
MOVING_SPEED_MAX = 2.8
FRAGILE_STAND_FRAMES = FPS  # 站1秒后爆碎（60帧）

IMG_DIR = r'I:\plane_game2\img'

BTN_W, BTN_H = 160, 50
BTN_RADIUS   = 12

# ── 浮空实体定义表 ────────────────────────────────────────────────────────────
ENTITY_DEFS = {
    'pet_star_cloud': {
        'img_dir':      'pet_star_cloud',
        'frame_count':  4,
        'size':         70,
        'score_delta':  +100,
        'speed_min':    0.5,
        'speed_max':    1.5,
        'spawn_chance': 0.003,
        'max_count':    2,
        'anim_speed':   8,
        'margin':       10,
    },
    'monster1': {
        'img_dir':      'monster1',
        'frame_count':  6,
        'size':         75,
        'score_delta':  -50,
        'speed':        2.2,      # 追踪速度（统一）
        'spawn_chance': 0.003,    # 降低出现频率（原0.004）
        'max_count':    2,        # 降低同时数量（原3）
        'anim_speed':   5,
        'margin':       12,
        'behavior':     'chase',  # 标记为追踪型
    },
    'monster2': {
        'img_dir':      'thunder_cloud',
        'frame_files':  [
            'thunder_cloud_smile.png',
            'thunder_cloud_happy.png',
            'thunder_cloud_surprise.png',
            'thunder_cloud_angry.png',
            'thunder_cloud_shy.png',
            'thunder_cloud_fight.png',
        ],
        'frame_count':  6,
        'size':         80,
        'score_delta':  -500,
        'speed_min':    0.8,
        'speed_max':    2.0,
        'spawn_chance': 0.0015,
        'max_count':    2,
        'anim_speed':   7,
        'margin':       10,
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


# ── 木板基类 ──────────────────────────────────────────────────────────────────
class Plank:
    def __init__(self, x, y, ptype, w, image):
        self.x     = float(x)
        self.y     = float(y)
        self.type  = ptype
        self.w     = w
        self.image = image
        self.alive = True

    def update(self):
        pass   # 子类重写

    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), self.w, PLANK_H)

    def draw(self, surf):
        surf.blit(self.image, (int(self.x), int(self.y)))


class PlankNormal(Plank):
    """普通固定板 / 紫楹板：不动。"""
    pass


class PlankMoving(Plank):
    """青蓝板：左右匀速移动，碰到边界反弹。"""
    def __init__(self, x, y, w, image):
        super().__init__(x, y, TYPE_MOVING, w, image)
        speed = random.uniform(MOVING_SPEED_MIN, MOVING_SPEED_MAX)
        self.vx = speed if random.random() < 0.5 else -speed

    def update(self):
        self.x += self.vx
        if self.x < 0:
            self.x = 0
            self.vx = abs(self.vx)   # 反弹向右
        elif self.x + self.w > SCREEN_W:
            self.x = SCREEN_W - self.w
            self.vx = -abs(self.vx)  # 反弹向左


class PlankFragile(Plank):
    """玄棕板：玩家站上去超过1秒后爆碎。"""
    def __init__(self, x, y, w, image):
        super().__init__(x, y, TYPE_FRAGILE, w, image)
        self.stand_timer = 0      # 玩家站在上面的帧计数
        self.cracking    = False  # 是否已开始倒计时
        self._flash      = 0      # 闪烁计时，用于视觉提示

    def start_crack(self):
        self.cracking = True

    def update(self):
        if self.cracking:
            self.stand_timer += 1
            self._flash += 1
            if self.stand_timer >= FRAGILE_STAND_FRAMES:
                self.alive = False
        else:
            # 不站就重置
            self.stand_timer = 0
            self._flash = 0

    def draw(self, surf):
        # 最后0.5秒快速闪烁提示即将爆碎
        remaining = FRAGILE_STAND_FRAMES - self.stand_timer
        if self.cracking and remaining < FPS // 2:
            if (self._flash // 4) % 2 == 0:
                return   # 闪烁：跳过绘制
        surf.blit(self.image, (int(self.x), int(self.y)))


# ── 浮空实体（pet / monster） ─────────────────────────────────────────────────
class FloatingEntity:
    def __init__(self, kind, frames, x, y, vx, size, score_delta, anim_speed, margin):
        self.kind        = kind
        self.frames      = frames
        self.x           = float(x)
        self.y           = float(y)
        self.vx          = vx
        self.size        = size
        self.score_delta = score_delta
        self.anim_speed  = anim_speed
        self.margin      = margin
        self.frame_idx   = 0
        self.frame_timer = 0
        self.alive       = True

    def update(self, target_x=None, target_y=None):
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


class ChasingEntity(FloatingEntity):
    """追踪型实体：朝主角方向移动，离屏销毁。"""
    def __init__(self, kind, frames, x, y, speed, size, score_delta, anim_speed, margin):
        super().__init__(kind, frames, x, y, 0, size, score_delta, anim_speed, margin)
        self.speed = speed
        self.vy = 0.0

    def update(self, target_x=None, target_y=None):
        if target_x is None or target_y is None:
            self.alive = False
            return

        # 计算朝向主角的单位向量
        cx = self.x + self.size / 2
        cy = self.y + self.size / 2
        dx = target_x - cx
        dy = target_y - cy
        dist = (dx**2 + dy**2) ** 0.5

        if dist < 5:  # 贴脸时停止
            self.vx = self.vy = 0
        else:
            self.vx = (dx / dist) * self.speed
            self.vy = (dy / dist) * self.speed

        self.x += self.vx
        self.y += self.vy

        # 离开屏幕范围销毁（不只左右，上下也算）
        if (self.x + self.size < -50 or self.x > SCREEN_W + 50 or
                self.y + self.size < -50 or self.y > SCREEN_H + 50):
            self.alive = False
            return

        # 帧动画
        self.frame_timer += 1
        if self.frame_timer >= self.anim_speed:
            self.frame_timer = 0
            self.frame_idx = (self.frame_idx + 1) % len(self.frames)


# ── 分数弹出文字 ──────────────────────────────────────────────────────────────
class ScorePopup:
    DURATION = 55

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

    def __init__(self, frames):
        self.frames_right = frames                                       # 原始朝右帧
        self.frames_left  = [pygame.transform.flip(f, True, False)      # 水平翻转朝左
                             for f in frames]
        self.frame_idx    = 0
        self.frame_timer  = 0
        self.facing_left  = False
        self.image        = frames[0]

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

    def update(self, keys):
        if self.going_up:
            if keys[pygame.K_LEFT]:
                self.vx = max(self.vx - 1.2, -MOVE_SPEED)
                self.facing_left = True
            elif keys[pygame.K_RIGHT]:
                self.vx = min(self.vx + 1.2, MOVE_SPEED)
                self.facing_left = False
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

        # 帧动画 + 朝向选帧
        self.frame_timer += 1
        if self.frame_timer >= CLOUD_ANIM_SPEED:
            self.frame_timer = 0
            self.frame_idx = (self.frame_idx + 1) % len(self.frames_right)
        frames = self.frames_left if self.facing_left else self.frames_right
        self.image = frames[self.frame_idx]

    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), CLOUD_W, CLOUD_H)


# ── 游戏主体 ──────────────────────────────────────────────────────────────────
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption('云端冲天 · Cloud Ascent')
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
        pl = os.path.join(IMG_DIR, 'plank')

        # 主角 Aquafluff 4帧
        aq = os.path.join(IMG_DIR, 'Aquafluff')
        self.cloud_frames = [
            load_img(os.path.join(aq, f'{i}.png'), CLOUD_W, CLOUD_H)
            for i in range(1, 5)
        ]

        # 紫楹板原图（备用哈希文件名）
        purple_path = os.path.join(pl, 'plank_purple.png')
        if not os.path.exists(purple_path):
            purple_path = os.path.join(pl, 'e25020e35571a32027123e80514d8158_16.png')

        # 原始未缩放的木板源图（Plank 构造时按宽度缩放）
        self.plank_src = {
            TYPE_BEIGE:   pygame.image.load(os.path.join(pl, 'plank_beige.png')).convert_alpha(),
            TYPE_PURPLE:  pygame.image.load(purple_path).convert_alpha(),
            TYPE_MOVING:  pygame.image.load(os.path.join(pl, 'plank_cyan.png')).convert_alpha(),
            TYPE_FRAGILE: pygame.image.load(os.path.join(pl, 'plank_darkbrown.png')).convert_alpha(),
        }

        self.bg = make_gradient_bg()

        # 浮空实体帧
        self.entity_frames = {}
        for kind, cfg in ENTITY_DEFS.items():
            d = os.path.join(IMG_DIR, cfg['img_dir'])
            files = cfg.get('frame_files') or [f'{i}.png' for i in range(1, cfg['frame_count'] + 1)]
            self.entity_frames[kind] = [
                load_img(os.path.join(d, f), cfg['size'], cfg['size'])
                for f in files
            ]
            log(f'加载 {kind} 共 {len(files)} 帧')

    # ── 重置 ──────────────────────────────────────────────────────────────────
    def reset(self):
        self.total_scroll = 0
        self.entity_bonus = 0
        self.game_over    = False

        self.cloud    = Cloud(self.cloud_frames)
        self.planks   = []
        self.entities = []
        self.popups   = []

        ground_y = SCREEN_H - 130
        self._spawn_plank(SCREEN_W // 2 - 90, ground_y, TYPE_BEIGE, w=180)

        self.cloud.x = float(SCREEN_W // 2 - CLOUD_W // 2)
        self.cloud.y = float(ground_y - CLOUD_H)

        self._fill_planks_above(ground_y)
        self.cloud.do_jump()
        log('游戏重置完成')

    @property
    def score(self):
        return max(0, int(self.total_scroll / 8) + self.entity_bonus)

    # ── 木板工厂 ──────────────────────────────────────────────────────────────
    def _make_image(self, ptype, w):
        return pygame.transform.smoothscale(self.plank_src[ptype], (w, PLANK_H))

    def _spawn_plank(self, x, y, ptype, w=None):
        if w is None:
            w = random.randint(PLANK_W_MIN, PLANK_W_MAX)
        img = self._make_image(ptype, w)
        if ptype == TYPE_MOVING:
            self.planks.append(PlankMoving(x, y, w, img))
        elif ptype == TYPE_FRAGILE:
            self.planks.append(PlankFragile(x, y, w, img))
        else:
            self.planks.append(PlankNormal(x, y, ptype, w, img))

    def _random_ptype(self):
        r = random.random()
        if r < PURPLE_CHANCE:
            return TYPE_PURPLE
        r -= PURPLE_CHANCE
        if r < FRAGILE_CHANCE:
            return TYPE_FRAGILE
        return TYPE_BEIGE

    def _horiz_reachable(self, prev_x, prev_w, new_x, new_w):
        """判断从上一块板能否横向跳到新板（板面边缘间距 <= MAX_HORIZ_REACH）。"""
        prev_right = prev_x + prev_w
        new_right  = new_x + new_w
        gap = max(0, max(prev_x, new_x) - min(prev_right, new_right))
        return gap <= MAX_HORIZ_REACH

    def _gen_one_plank(self, y, prev_x, prev_w):
        """生成一块板。若随机位置横向不可达，自动插入移动板作为跳板。"""
        ptype = self._random_ptype()
        w     = random.randint(PLANK_W_MIN, PLANK_W_MAX)
        x     = random.randint(0, max(0, SCREEN_W - w))

        # 检测横向是否可达
        if not self._horiz_reachable(prev_x, prev_w, x, w):
            # 在两板之间竖向中点插一块移动板
            bridge_w = random.randint(PLANK_W_MIN, PLANK_W_MAX)
            # 移动板初始位置放在两板横向中间
            bridge_x = int((prev_x + prev_w / 2 + x + w / 2) / 2 - bridge_w / 2)
            bridge_x = max(0, min(bridge_x, SCREEN_W - bridge_w))
            bridge_y = y + PLANK_GAP_MIN // 2   # 在当前板下方一半间距处（世界坐标往下=y大）
            self._spawn_plank(bridge_x, bridge_y, TYPE_MOVING, bridge_w)
            log(f'横向过远 自动插入移动板 bridge_x={bridge_x} bridge_y={bridge_y}')

        self._spawn_plank(x, y, ptype, w)
        return x, w

    def _fill_planks_above(self, from_y):
        prev_x, prev_w = SCREEN_W // 2 - 90, 180
        y = from_y - random.randint(PLANK_GAP_MIN, PLANK_GAP_MIN + 20)
        while y > -SCREEN_H * 0.5:
            prev_x, prev_w = self._gen_one_plank(y, prev_x, prev_w)
            y -= random.randint(PLANK_GAP_MIN, PLANK_GAP_MAX)

    def _ensure_planks_above(self):
        alive_planks = [p for p in self.planks if p.alive]
        if not alive_planks:
            return
        top_y     = min(p.y for p in alive_planks)
        top_plank = min(alive_planks, key=lambda p: p.y)
        prev_x, prev_w = int(top_plank.x), int(top_plank.w)
        while top_y > -SCREEN_H * 0.3:
            gap    = random.randint(PLANK_GAP_MIN, PLANK_GAP_MAX)
            top_y -= gap
            prev_x, prev_w = self._gen_one_plank(top_y, prev_x, prev_w)

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

    # ── 主更新 ────────────────────────────────────────────────────────────────
    def update(self, keys):
        if self.game_over:
            return

        self.cloud.update(keys)

        if self.cloud.y < Cloud.SCROLL_THRESHOLD:
            dy = Cloud.SCROLL_THRESHOLD - self.cloud.y
            self._scroll(dy)
            self.cloud.y = Cloud.SCROLL_THRESHOLD

        # 木板更新（移动、易碎计时）
        for p in self.planks:
            p.update()

        self._ensure_planks_above()
        # 清理：出屏幕下方 或 已销毁
        self.planks = [p for p in self.planks if p.alive and p.y < SCREEN_H + 60]

        # 木板碰撞（仅下落阶段）
        if self.cloud.falling:
            c_rect            = self.cloud.rect()
            cloud_bottom      = self.cloud.y + CLOUD_H
            cloud_bottom_prev = cloud_bottom - self.cloud.vy

            landed_plank = None
            for p in self.planks:
                pr = p.rect()
                if (c_rect.right > pr.left and c_rect.left < pr.right and
                        cloud_bottom_prev <= pr.top + 6 and
                        cloud_bottom >= pr.top):
                    landed_plank = p
                    break

            if landed_plank is not None:
                self.cloud.y       = landed_plank.y - CLOUD_H
                self.cloud.falling = False
                boosted = (landed_plank.type == TYPE_PURPLE)
                if boosted:
                    log(f'踩中紫楹木！跳跃翻倍 得分={self.score}')
                self.cloud.do_jump(boosted=boosted)

                # 易碎板：踩上去开始倒计时
                if isinstance(landed_plank, PlankFragile):
                    landed_plank.start_crack()
                    log('踩上易碎板，开始倒计时')

            # 如果踩着的易碎板已经炸了（理论上下帧才销毁，这里不影响）
        else:
            # 站在某块板上（going_up=False, falling=False = 刚落地瞬间，已由do_jump接管）
            # 易碎板：如果玩家不在空中且站在其上，持续累计
            # 实际上 do_jump 会立即让玩家再起跳，所以 fragile 的倒计时逻辑
            # 在 update() 里每帧调用 p.update() 即可，start_crack 已在落地时触发
            pass

        # 浮空实体生成
        for kind, cfg in ENTITY_DEFS.items():
            count = sum(1 for e in self.entities if e.kind == kind)
            if count < cfg['max_count'] and random.random() < cfg['spawn_chance']:
                size = cfg['size']
                py = random.randint(int(SCREEN_H * 0.1), int(SCREEN_H * 0.75))

                if cfg.get('behavior') == 'chase':
                    # 追踪型：从屏幕边缘随机位置出现
                    from_right = random.random() < 0.5
                    px = SCREEN_W + size if from_right else -size
                    self.entities.append(ChasingEntity(
                        kind, self.entity_frames[kind],
                        px, py, cfg['speed'],
                        size, cfg['score_delta'], cfg['anim_speed'], cfg['margin']
                    ))
                    log(f'{kind}(追踪型) 出现 x={px:.0f}')
                else:
                    # 普通横向移动型
                    from_right = random.random() < 0.5
                    vx = random.uniform(cfg['speed_min'], cfg['speed_max'])
                    if from_right:
                        px, vx = SCREEN_W, -vx
                    else:
                        px = -size
                    self.entities.append(FloatingEntity(
                        kind, self.entity_frames[kind],
                        px, py, vx,
                        size, cfg['score_delta'], cfg['anim_speed'], cfg['margin']
                    ))
                    tag = '+奖励' if cfg['score_delta'] > 0 else '-惩罚'
                    log(f'{kind}({tag}) 出现 x={px:.0f} vx={vx:.2f}')

        # 实体碰撞
        c_rect = self.cloud.rect()
        target_cx = self.cloud.x + CLOUD_W / 2
        target_cy = self.cloud.y + CLOUD_H / 2
        for e in self.entities:
            e.update(target_cx, target_cy)
            if e.alive and c_rect.colliderect(e.rect()):
                e.alive = False
                e.alive = False
                self.entity_bonus += e.score_delta
                cx = int(e.x + e.size / 2)
                cy = int(e.y)
                self.popups.append(ScorePopup(cx, cy, e.score_delta, self.font_popup))
                sign = '+' if e.score_delta > 0 else ''
                log(f'碰到 {e.kind}！{sign}{e.score_delta}分 当前总分={self.score}')
        self.entities = [e for e in self.entities if e.alive]

        # 弹出文字
        for pp in self.popups:
            pp.update()
        self.popups = [pp for pp in self.popups if pp.alive]

        # 坠落结束
        if self.cloud.y > SCREEN_H + 40:
            self.game_over = True
            log(f'游戏结束 得分={self.score}')

    # ── 渲染 ──────────────────────────────────────────────────────────────────
    def draw(self, mouse_pos):
        self.screen.blit(self.bg, (0, 0))

        for p in self.planks:
            p.draw(self.screen)

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
            self._draw_centered('游戏结束！',           self.font_big, (255, 90, 90),   cx, SCREEN_H // 2 - 90)
            self._draw_centered(f'得分: {self.score}',  self.font_big, (255, 255, 255), cx, SCREEN_H // 2 - 30)

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
