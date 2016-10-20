from nvm.pmemobj import PersistentObjectPool

with PersistentObjectPool('hello_world.pmem', flag='c') as pool:
    if pool.root is None:
        name = input("What is your name? ")
        pool.root = name
    print("Hello, {}".format(pool.root))
