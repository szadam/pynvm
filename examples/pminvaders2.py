from __future__ import division
import argparse
import curses
import sys
from contextlib import contextmanager
from random import randrange, randint
from time import sleep

from nvm.pmemobj import (PersistentObjectPool, PersistentList, PersistentDict,
                         PersistentObject)

import logging
import logging.handlers
sout = logging.StreamHandler(sys.stderr)
sout.setFormatter(logging.Formatter('%(asctime)s %(name)-15s %(levelname)-8s %(message)s'))
mout = logging.handlers.MemoryHandler(100*10000, target=sout)
mout.setFormatter(logging.Formatter('%(asctime)s %(name)-15s %(levelname)-8s %(message)s'))
root = logging.getLogger()
#root.setLevel(logging.DEBUG)
root.addHandler(sout)
#sout.addFilter(logging.Filter('nvm.pmemobj.dict'))

# We're slow, so shorten the timers and increase the delay.  Even with this
# the pmem version is slower than the non-pmem version.
STEP = 50000/1000000
MAX_GSTATE_TIMER = 100
MIN_GSTATE_TIMER = 50
MAX_ALIEN_TIMER = 10
MAX_PLAYER_TIMER = 10
MAX_BULLET_TIMER = 5
MAX_STAR1_TIMER = 2
MAX_STAR2_TIMER = 1
ALIEN_TIMER_LEVEL_FACTOR = 1

GAME_WIDTH = 50
GAME_HEIGHT = 25

ALIENS_ROW = 4
ALIENS_COL = 18

C_UNKNOWN = 0
C_PLAYER = 1
C_ALIEN = 2
C_BULLET = 3
C_STAR = 4
C_INTRO = 5

EVENT_PLAYER_KILLED = 0
EVENT_ALIENS_KILLED = 1
EVENT_BOUNCE = 2

CH_Q = ord('q')
CH_SP = ord(' ')
CH_O = ord('o')
CH_P = ord('p')

parser = argparse.ArgumentParser()
parser.add_argument('fn', help="Persistent memory game file")
parser.add_argument('--no-pmem', action='store_true',
                    help="Use dummy PersistentObjectPool instead of real one")

def _new(typ, *args, **kw):
    if typ == PersistentList:
        return list(*args, **kw)
    if typ == PersistentDict:
        return dict(*args, **kw)
    else:
        typ.__bases__ = (Dummy,)
        obj = typ(*args, **kw)
        obj._v_init()
        return obj
class Dummy(object):
    class _p_mm(object):
        @staticmethod
        def new(typ, *args, **kw):
            return _new(typ, *args, **kw)
        @staticmethod
        @contextmanager
        def transaction():
            yield None
    def _v_init(self):
        pass
class DummyPersistentObjectPool:
    def __init__(self, *args, **kw):
        self.root = None
    def new(self, typ, *args, **kw):
        obj = _new(typ, *args, **kw)
        return _new(typ, *args, **kw)
    @contextmanager
    def transaction(self):
        yield None
    def close(self):
        pass
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


class Player(PersistentObject):

    y = GAME_HEIGHT - 1

    def __init__(self):
        self.x = GAME_WIDTH // 2
        self.timer = 1


class Alien(PersistentObject):

    def __init__(self, x, y):
        self.x = x
        self.y = y


class Bullet(PersistentObject):

    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.timer = 1


class Star(PersistentObject):

    def __init__(self, x, y, c, timer):
        self.x = x
        self.y = y
        self.c = c
        self.timer = timer


class Screen(object):

    closed = True

    def __init__(self):
        screen = self.screen = curses.initscr()
        self.closed = False
        curses.start_color()
        curses.init_pair(C_PLAYER, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(C_ALIEN, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(C_BULLET, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(C_STAR, curses.COLOR_WHITE, curses.COLOR_BLACK)
        curses.init_pair(C_INTRO, curses.COLOR_BLUE, curses.COLOR_BLACK)
        screen.nodelay(True)
        curses.curs_set(0)
        screen.keypad(True)

    def draw_border(self):
        screen = self.screen
        for x in range(GAME_WIDTH+1):
            screen.addch(0, x, curses.ACS_HLINE)
            screen.addch(GAME_HEIGHT, x, curses.ACS_HLINE)
        for y in range(GAME_HEIGHT+1):
            screen.addch(y, 0, curses.ACS_VLINE)
            screen.addch(y, GAME_WIDTH, curses.ACS_VLINE)
        screen.addch(0, 0, curses.ACS_ULCORNER)
        screen.addch(GAME_HEIGHT, 0, curses.ACS_LLCORNER)
        screen.addch(0, GAME_WIDTH, curses.ACS_URCORNER)
        screen.addch(GAME_HEIGHT, GAME_WIDTH, curses.ACS_LRCORNER)

    def printw(self, y, x, string):
        for i in range(x, x + len(string)):
            self.screen.addch(y, i, string[i - x])

    def draw_title(self):
        screen = self.screen
        x = (GAME_WIDTH -40) // 2
        y = GAME_HEIGHT // 2 - 2
        screen.attron(curses.color_pair(C_INTRO))
        self.printw(y + 0, x, "#### #   # ### #   # #   #     ###   ###")
        self.printw(y + 1, x, "#  # ## ##  #  ##  # #   #       #   # #")
        self.printw(y + 2, x, "#### # # #  #  # # #  # #      ###   # #")
        self.printw(y + 3, x, "#    # # #  #  #  ##  # #      #     # #")
        self.printw(y + 4, x, "#    #   # ### #   #   #       ### # ###")
        screen.attroff(curses.color_pair(C_INTRO))
        self.printw(y + 6, x, "      Press 'space' to resume           ")
        self.printw(y + 7, x, "      Press 'q' to quit                 ")

    def draw_score(self, level, score, high_score):
        self.printw(1, 1, "Level: {:5} Score: {} | {}".format(
                    level,
                    score,
                    high_score))

    def erase(self):
        self.screen.erase()

    def getch(self):
        return self.screen.getch()

    def refresh(self):
        self.screen.refresh()

    def addch(self, y, x, c, color):
        self.screen.addch(y, x, c, color)

    def close(self):
        if not self.closed:
            curses.endwin()

    def __del__(self):
        self.close()


class PMInvaders2(PersistentObject):

    def __init__(self):
        # Game init
        self.timer = 1
        self.score = 0
        self.high_score = 0
        self.level = 0
        self.new_level = 1
        self.dx = 1
        self.dy = 0
        self.player = self._p_mm.new(Player)
        self.aliens = self._p_mm.new(PersistentList)
        self.bullets = self._p_mm.new(PersistentList)
        self.stars = self._p_mm.new(PersistentList)

    def _v__init__(self):
        self._v_screen = Screen()

    def close(self):
        self._v_screen.close()

    def create_star(self, x, y):
        c = '*' if randint(0, 1) else '.'
        timer = MAX_STAR1_TIMER if c == '.' else MAX_STAR2_TIMER
        return self._p_mm.new(Star, x=x, y=y, c=c, timer=timer)

    def create_stars(self):
        # C version prepends to list; I'm appending so list is reversed.  Our
        # append is as atomic as the C code's linked list pointer assignment.
        for x in range(1, GAME_WIDTH):
            if randrange(0, 100) < 4:
                self.stars.append(self.create_star(x, 1))

    def draw_star(self, star):
        self._v_screen.addch(star.y, star.x, star.c, curses.color_pair(C_STAR))

    def process_stars(self):
        new_line = False
        with self._p_mm.transaction():
            stars = self.stars
            for star in list(stars):
                star.timer -= 1
                if not star.timer:
                    if star.c == '.':
                        star.timer = MAX_STAR1_TIMER
                        new_line = True
                    else:
                        star.timer = MAX_STAR2_TIMER
                    star.y += 1
                self.draw_star(star)
                if star.y >= GAME_HEIGHT-1:
                    stars.remove(star)
            if new_line:
                self.create_stars()

    def intro_loop(self):
        exit = None
        while exit not in (CH_Q, CH_SP):
            self._v_screen.erase()
            self._v_screen.draw_border()
            if not self.stars:
                self.create_stars()
            self.process_stars()
            self._v_screen.draw_title()
            sleep(STEP)
            self._v_screen.refresh()
            exit = self._v_screen.getch()
        return exit == CH_Q

    def remove_aliens(self):
        self.aliens.clear()

    def create_aliens(self):
        aliens = self.aliens
        for x in range(ALIENS_COL):
            for y in range(ALIENS_ROW):
                aliens.append(self._p_mm.new(Alien,
                              x=GAME_WIDTH // 2 - ALIENS_COL + x * 2, y=y + 3))

    def create_new_level(self):
        with self._p_mm.transaction():
            self.remove_aliens()
            self.create_aliens()
            if self.new_level > 0 or self.level > 1:
                self.level += self.new_level
            self.new_level = 0
            self.dx = 1
            self.dy = 0
            self.timer = (MAX_ALIEN_TIMER
                          - ALIEN_TIMER_LEVEL_FACTOR
                          * (self.level - 1))

    def update_score(self, delta):
        if delta < 0 and not self.score:
            return
        self.score += delta
        if self.score < 0:
            self.score = 0
        if self.score > self.high_score:
            self.high_score = self.score

    def move_aliens(self):
        aliens = self.aliens
        player = self.player
        dx = self.dx
        dy = self.dy
        if not aliens:
            return EVENT_ALIENS_KILLED
        event = None
        for alien in aliens:
            if dy:
                alien.y += dy
            if dx:
                alien.x += dx
            if alien.y >= player.y:
                event = EVENT_PLAYER_KILLED
            elif (dy == 0
                  and alien.x >= GAME_WIDTH - 2
                  or alien.x <= 2):
                event = EVENT_BOUNCE
        return event

    def process_aliens(self):
        with self._p_mm.transaction():
            self.timer -= 1
            if not self.timer:
                self.timer = (MAX_ALIEN_TIMER
                              - ALIEN_TIMER_LEVEL_FACTOR
                              * (self.level - 1))
                event = self.move_aliens()
                if event == EVENT_ALIENS_KILLED:
                    self.new_level = 1
                elif event == EVENT_PLAYER_KILLED:
                    curses.flash()
                    curses.beep()
                    self.new_level = -1
                    self.update_score(-100)
                elif event == EVENT_BOUNCE:
                    self.dy = 1
                    self.dx = -self.dx
                elif self.dy:
                    self.dy = 0
        for alien in self.aliens:
            self._v_screen.addch(alien.y, alien.x,
                                 curses.ACS_DIAMOND, curses.color_pair(C_ALIEN))

    def process_collision(self, bullet):
        aliens = self.aliens
        with self._p_mm.transaction():
            for alien in list(aliens):
                if (bullet.x == alien.x
                        and bullet.y == alien.y):
                    self.update_score(1)
                    aliens.remove(alien)
                    return True
        return False

    def process_bullets(self):
        with self._p_mm.transaction():
            for bullet in list(self.bullets):
                bullet.timer -= 1
                if not bullet.timer:
                    bullet.timer = MAX_BULLET_TIMER
                    bullet.y -= 1
                self._v_screen.addch(bullet.y, bullet.x,
                                     curses.ACS_BULLET,
                                     curses.color_pair(C_BULLET))
                if bullet.y <= 0 or self.process_collision(bullet):
                    self.bullets.remove(bullet)

    def process_player(self, ch):
        with self._p_mm.transaction():
            player = self.player
            player.timer -= 1
            if ch in (CH_O, curses.KEY_LEFT):
                dstx = player.x - 1
                if dstx:
                    player.x = dstx
            elif ch in (CH_P, curses.KEY_RIGHT):
                dstx = player.x + 1
                if dstx != GAME_WIDTH:
                    player.x = dstx
            elif ch == CH_SP and player.timer <= 0:
                player.timer = MAX_PLAYER_TIMER
                self.bullets.append(self._p_mm.new(Bullet,
                    x=player.x, y=player.y-1))
        self._v_screen.addch(player.y, player.x,
                             curses.ACS_DIAMOND,
                             curses.color_pair(C_PLAYER))

    def game_loop(self):
        ch = None
        while ch != CH_Q:
            ch = self._v_screen.getch()
            self._v_screen.erase()
            self._v_screen.draw_score(self.level, self.score, self.high_score)
            self._v_screen.draw_border()
            with self._p_mm.transaction():
                if self.new_level:
                    self.create_new_level()
                self.process_aliens()
                self.process_bullets()
                self.process_player(ch)
            sleep(STEP)
            self._v_screen.refresh()

    def run(self):
        exit = self.intro_loop()
        if exit:
            return
        self.game_loop()

if __name__ == '__main__':
    args = parser.parse_args()
    if args.no_pmem:
        PersistentObjectPool = DummyPersistentObjectPool
    pop = PersistentObjectPool(args.fn, flag='c', debug=True)
    if pop.root is None:
        pop.root = pop.new(PMInvaders2)
    try:
        pop.root.run()
    finally:
        pop.root.close()
        mout.flush()
        pop.close()
