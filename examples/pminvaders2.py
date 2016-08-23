from __future__ import division
import argparse
import curses
import sys
from contextlib import contextmanager
from random import randrange, randint
from time import sleep

from nvm.pmemobj import PersistentObjectPool, PersistentList, PersistentDict

import logging
import logging.handlers
sout = logging.StreamHandler(sys.stdout)
sout.setFormatter(logging.Formatter('%(asctime)s %(name)-15s %(levelname)-8s %(message)s'))
mout = logging.handlers.MemoryHandler(100*10000, target=sout)
mout.setFormatter(logging.Formatter('%(asctime)s %(name)-15s %(levelname)-8s %(message)s'))
root = logging.getLogger()
#root.setLevel(logging.DEBUG)
root.addHandler(mout)
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

PLAYER_Y = GAME_HEIGHT - 1

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

class DummyPersistentObjectPool:
    def __init__(self, *args, **kw):
        self.root = None
        pass
    def new(self, typ, *args, **kw):
        if typ == PersistentList:
            return list(*args, **kw)
        if typ == PersistentDict:
            return dict(*args, **kw)
    @contextmanager
    def transaction(self):
        yield None
    def close(self):
        pass
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


class PMInvaders2(object):

    closed = True

    def __init__(self, pop):
        self.pop = pop
        # curses init
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
        # Game init
        if pop.root is None:
            pop.root = pop.new(PersistentDict)
        if 'state' not in pop.root:
            pop.root['state'] = self.pop.new(PersistentDict,
                timer=1,
                score=0,
                high_score=0,
                level=0,
                new_level=1,
                dx=1,
                dy=0)
        if 'player' not in pop.root:
            pop.root['player'] = self.pop.new(PersistentDict,
                x=GAME_WIDTH // 2, timer=1)
        if 'aliens' not in pop.root:
            pop.root['aliens'] = self.pop.new(PersistentList)
        if 'bullets' not in pop.root:
            pop.root['bullets'] = self.pop.new(PersistentList)
        if 'stars' not in pop.root:
            pop.root['stars'] = self.pop.new(PersistentList)
        self.root = pop.root

    def close(self):
        curses.endwin()
        self.closed = True

    def __del__(self):
        if not self.closed:
            self.close()

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

    def create_star(self, x, y):
        c = '*' if randint(0, 1) else '.'
        timer = MAX_STAR1_TIMER if c == '.' else MAX_STAR2_TIMER
        return self.pop.new(PersistentDict, dict(x=x, y=y, c=c, timer=timer))

    def create_stars(self):
        # C version prepends to list; I'm appending so list is reversed.  Our
        # append is as atomic as the C code's linked list pointer assignment.
        for x in range(1, GAME_WIDTH):
            if randrange(0, 100) < 4:
                self.root['stars'].append(self.create_star(x, 1))

    def draw_star(self, star):
        self.screen.addch(star['y'], star['x'], star['c'],
                          curses.color_pair(C_STAR))

    def process_stars(self):
        new_line = False
        with self.pop.transaction():
            stars = self.root['stars']
            for star in list(stars):
                star['timer'] -= 1
                if not star['timer']:
                    if star['c'] == '.':
                        star['timer'] = MAX_STAR1_TIMER
                        new_line = True
                    else:
                        star['timer'] = MAX_STAR2_TIMER
                    star['y'] += 1
                self.draw_star(star)
                if star['y'] >= GAME_HEIGHT-1:
                    stars.remove(star)
            if new_line:
                self.create_stars()

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

    def intro_loop(self):
        exit = None
        while exit not in (CH_Q, CH_SP):
            exit = self.screen.getch()
            self.screen.erase()
            self.draw_border()
            if not self.root['stars']:
                self.create_stars()
            self.process_stars()
            self.draw_title()
            sleep(STEP)
            self.screen.refresh()
        return exit == CH_Q

    def draw_score(self):
        state = self.root['state']
        self.printw(1, 1, "Level: {:5} Score: {} | {}".format(
                    state['level'],
                    state['score'],
                    state['high_score']))

    def remove_aliens(self):
        self.root['aliens'].clear()

    def create_aliens(self):
        aliens = self.root['aliens']
        for x in range(ALIENS_COL):
            for y in range(ALIENS_ROW):
                aliens.append(self.pop.new(PersistentDict,
                              x=GAME_WIDTH // 2 - ALIENS_COL + x * 2, y=y + 3))

    def new_level(self):
        with self.pop.transaction():
            self.remove_aliens()
            self.create_aliens()
            state = self.root['state']
            if state['new_level'] > 0 or state['level'] > 1:
                state['level'] += state['new_level']
            state['new_level'] = 0
            state['dx'] = 1
            state['dy'] = 0
            state['timer'] = (MAX_ALIEN_TIMER
                              - ALIEN_TIMER_LEVEL_FACTOR
                              * (state['level'] - 1))

    def update_score(self, delta):
        state = self.root['state']
        if delta < 0 and not state['score']:
            return
        state['score'] += delta
        if state['score'] < 0:
            state['score'] = 0
        if state['score'] > state['high_score']:
            state['high_score'] = state['score']

    def move_aliens(self):
        aliens = self.root['aliens']
        player = self.root['player']
        state = self.root['state']
        dx = state['dx']
        dy = state['dy']
        if not aliens:
            return EVENT_ALIENS_KILLED
        event = None
        for alien in aliens:
            if dy:
                alien['y'] += dy
            if dx:
                alien['x'] += dx
            if alien['y'] >= PLAYER_Y:
                event = EVENT_PLAYER_KILLED
            elif (dy == 0
                  and alien['x'] >= GAME_WIDTH - 2
                  or alien['x'] <= 2):
                event = EVENT_BOUNCE
        return event

    def process_aliens(self):
        state = self.root['state']
        with self.pop.transaction():
            state['timer'] -= 1
            if not state['timer']:
                state['timer'] = (MAX_ALIEN_TIMER
                                  - ALIEN_TIMER_LEVEL_FACTOR
                                  * (state['level'] - 1))
                event = self.move_aliens()
                if event == EVENT_ALIENS_KILLED:
                    state['new_level'] = 1
                elif event == EVENT_PLAYER_KILLED:
                    curses.flash()
                    curses.beep()
                    state['new_level'] = -1
                    self.update_score(-100)
                elif event == EVENT_BOUNCE:
                    state['dy'] = 1
                    state['dx'] = -state['dx']
                elif state['dy']:
                    state['dy'] = 0
        for alien in self.root['aliens']:
            self.screen.addch(alien['y'], alien['x'],
                              curses.ACS_DIAMOND, curses.color_pair(C_ALIEN))

    def process_collision(self, bullet):
        aliens = self.root['aliens']
        with self.pop.transaction():
            for alien in list(aliens):
                if (bullet['x'] == alien['x']
                        and bullet['y'] == alien['y']):
                    self.update_score(1)
                    aliens.remove(alien)
                    return True
        return False

    def process_bullets(self):
        with self.pop.transaction():
            for bullet in list(self.root['bullets']):
                bullet['timer'] -= 1
                if not bullet['timer']:
                    bullet['timer'] = MAX_BULLET_TIMER
                    bullet['y'] -= 1
                self.screen.addch(bullet['y'], bullet['x'],
                                  curses.ACS_BULLET,
                                  curses.color_pair(C_BULLET))
                if bullet['y'] <= 0 or self.process_collision(bullet):
                    self.root['bullets'].remove(bullet)

    def process_player(self, ch):
        with self.pop.transaction():
            player = self.root['player']
            player['timer'] -= 1
            if ch in (CH_O, curses.KEY_LEFT):
                dstx = player['x'] - 1
                if dstx:
                    player['x'] = dstx
            elif ch in (CH_P, curses.KEY_RIGHT):
                dstx = player['x'] + 1
                if dstx != GAME_WIDTH:
                    player['x'] = dstx
            elif ch == CH_SP and player['timer'] <= 0:
                player['timer'] = MAX_PLAYER_TIMER
                self.root['bullets'].append(self.pop.new(PersistentDict,
                    x=player['x'], y=PLAYER_Y-1, timer=1))
        self.screen.addch(PLAYER_Y, player['x'],
                          curses.ACS_DIAMOND,
                          curses.color_pair(C_PLAYER))

    def game_loop(self):
        ch = None
        state = self.root['state']
        while ch != CH_Q:
            ch = self.screen.getch()
            self.screen.erase()
            self.draw_score()
            self.draw_border()
            with self.pop.transaction():
                if state['new_level']:
                    self.new_level()
                self.process_aliens()
                self.process_bullets()
                self.process_player(ch)
            sleep(STEP)
            self.screen.refresh()

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
    g = PMInvaders2(pop)
    try:
        g.run()
    finally:
        g.close()
        mout.flush()
        pop.close()
