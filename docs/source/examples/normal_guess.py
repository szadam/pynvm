import random
import sys

guesses = []
max = 50
name = input("Hello, what is your name? ")
number = random.randint(1, max)
print("{}, I've picked a number between 1 and {}.".format(name, max))

while len(guesses) < 6:
    print('Take a guess.')
    guess = int(input('> '))
    if guess in guesses:
        print("You already tried that number!")
        continue
    if guess < number:
        print('Your guess is too low.')
    if guess > number:
        print('Your guess is too high.')
    if guess == number:
        print('You guessed my number in {} tries, {}.'.format(
            len(guesses)+1, name))
        break
    guesses.append(guess)
else:
    print("Too many guesses, {}!"
          "  The number I was thinking of was {}".format(
                name, number))
