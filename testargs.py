def main():
    x = ('meow', 'grrr', 'purr')
    kitten(*x)

def kitten(*args):
    print(len(args))
    if len(args):
        for s in args:
            print(s)
    else: print('Miao.')

if __name__ == '__main__': main()