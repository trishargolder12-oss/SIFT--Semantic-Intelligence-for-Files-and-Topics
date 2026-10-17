import multiprocessing

from sift_indexer.__main__ import main


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()

