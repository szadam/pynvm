import random
import os

from nvm.pmemobj import open, PersistentObject, PersistentList

pool_fn = 'guessing_game2.pmem'


class GameError(Exception):
    pass

def reopen_game():
    if not os.path.isfile(pool_fn):
        raise GameError("No game in progress.  Use 'start_guessng'"
                        " to start one.")
    try:
        pool = open(pool_fn)
    except OSError as err:
        exc = GameError("Could not open game file: {}".format(err))
        try:
            os.remove(pool_fn)
        except OSError as err:
            raise GameError("Can't remove game file")
        raise GameError("Could not open game file, start again"
                        " with 'start_guessing'")
    if pool.root is None:
        pool.close()
        os.remove(pool_fn)
        raise("Looks like a game was aborted; start again with"
              " 'start_guessing'")
    return pool


class Guesser(PersistentObject):

    def __init__(self, name, maximum=50):
        self.name = name
        self.maximum = maximum
        self.number = random.randint(1, maximum)
        self.guesses = self._p_mm.new(PersistentList)
        self.lost = False
        self.done = False

    def _guess_to_int(self, s):
        try:
            guess = int(s)
        except ValueError as err:
            raise ValueError("Please specify an integer; {} is not"
                             "valid: {}".format(s, err))
        if guess < 1 or guess > self.maximum:
            raise ValueError("Come now, {}, a guess outside of the"
                             " range I told you won't get you"
                             " anywhere".format(self.name))
        return guess

    def check_guess(self, guess):
        guess = self._guess_to_int(guess)
        with self._p_mm.transaction():
            self.current_guess = guess
            if guess in self.guesses:
                self.current_outcome = 'SEEN'
            self.guesses.append(guess)
            if guess == self.number:
                self.current_outcome = 'EQUAL'
                self.done = True
            if len(self.guesses) > 6:
                self.lost = True
                self.done = True
            if guess < self.number:
                self.current_outcome = 'LOW'
            if guess > self.number:
                self.current_outcome = 'HIGH'
        return self.current_outcome

    def message(self, key):
        return getattr(self, 'msg_' + key)()

    def msg_START(self):
        return "{}, I've picked a number between 1 and {}.".format(
                    self.name, self.maximum)

    def msg_SEEN(self):
        return "You already tried {}".format(self.current_guess)

    def msg_EQUAL(self):
        return "You guessed my number in {} tries, {}.".format(
                    len(self.guesses), self.name)

    def msg_LOW(self):
        return "Your guess is too low."

    def msg_HIGH(self):
        return "Your guess is too high."

    def msg_LOST(self):
        return ("Too many guesses, {}!"
                "  The number I was thinking of was {}".format(
                    self.name, self.number))
