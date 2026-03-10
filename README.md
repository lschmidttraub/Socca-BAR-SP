# Soccer Analytics Barcelona Set Pieces

This repository is for developing analyses of Barcelona's UCL games, focusing on set pieces.

## Layout

`data/`: contains all the **proprietary** data used for the analyses
`src/`: contains all the code for the analyses
`assets/`: generated graphs/visualizations. We are allowed to upload data analyses as long as the original data isn't reconstructible from them
`.claude/`: contains the settings file for Claude Code that denies it read access

## Analyses

1. Pass counter

## Layout for the data directory

For reproducibility, here's the layout of my `data/` directory (output of `tree data/`):

```

data/
├── clip.mp4
├── matches.csv
├── README.md
├── statsbomb
│   ├── 4028813.json
│   ├── 4028813_lineups.json
│   ├── 4028814.json
│   ├── 4028814_lineups.json
│   ├── 4028815.json
│   ├── 4028815_lineups.json
│   ├── 4028816.json
│   ├── 4028816_lineups.json
│   ├── 4028817.json
│   ├── 4028817_lineups.json
│   ├── 4028818.json
│   ├── 4028818_lineups.json
│   ├── 4028819.json
│   ├── 4028819_lineups.json
│   ├── 4028820.json
│   ├── 4028820_lineups.json
│   ├── 4028821.json
│   ├── 4028821_lineups.json
│   ├── 4028822.json
│   ├── 4028822_lineups.json
│   ├── 4028823.json
│   ├── 4028823_lineups.json
│   ├── 4028824.json
│   ├── 4028824_lineups.json
│   ├── 4028825.json
│   ├── 4028825_lineups.json
│   ├── 4028826.json
│   ├── 4028826_lineups.json
│   ├── 4028827.json
│   ├── 4028827_lineups.json
│   ├── 4028828.json
│   ├── 4028828_lineups.json
│   ├── 4028829.json
│   ├── 4028829_lineups.json
│   ├── 4028830.json
│   ├── 4028830_lineups.json
│   ├── 4028831.json
│   ├── 4028831_lineups.json
│   ├── 4028832.json
│   ├── 4028832_lineups.json
│   ├── 4028833.json
│   ├── 4028833_lineups.json
│   ├── 4028834.json
│   ├── 4028834_lineups.json
│   ├── 4028835.json
│   ├── 4028835_lineups.json
│   ├── 4028836.json
│   ├── 4028836_lineups.json
│   ├── 4028837.json
│   ├── 4028837_lineups.json
│   ├── 4028838.json
│   ├── 4028838_lineups.json
│   ├── 4028839.json
│   ├── 4028839_lineups.json
│   ├── 4028840.json
│   ├── 4028840_lineups.json
│   ├── 4028841.json
│   ├── 4028841_lineups.json
│   ├── 4028842.json
│   ├── 4028842_lineups.json
│   ├── 4028843.json
│   ├── 4028843_lineups.json
│   ├── 4028844.json
│   ├── 4028844_lineups.json
│   ├── 4028845.json
│   ├── 4028845_lineups.json
│   ├── 4028846.json
│   ├── 4028846_lineups.json
│   ├── 4028847.json
│   ├── 4028847_lineups.json
│   ├── 4028848.json
│   ├── 4028848_lineups.json
│   ├── 4028849.json
│   ├── 4028849_lineups.json
│   ├── 4028882.json
│   ├── 4028882_lineups.json
│   ├── 4028883.json
│   ├── 4028883_lineups.json
│   ├── 4028884.json
│   ├── 4028884_lineups.json
│   ├── 4028885.json
│   ├── 4028885_lineups.json
│   ├── 4028886.json
│   ├── 4028886_lineups.json
│   ├── 4028887.json
│   ├── 4028887_lineups.json
│   ├── 4028888.json
│   ├── 4028888_lineups.json
│   ├── 4028889.json
│   ├── 4028889_lineups.json
│   ├── 4028890.json
│   ├── 4028890_lineups.json
│   ├── 4028891.json
│   ├── 4028891_lineups.json
│   ├── 4028892.json
│   ├── 4028892_lineups.json
│   ├── 4028893.json
│   ├── 4028893_lineups.json
│   ├── 4028894.json
│   ├── 4028894_lineups.json
│   ├── 4028895.json
│   ├── 4028895_lineups.json
│   ├── 4028896.json
│   ├── 4028896_lineups.json
│   ├── 4028897.json
│   ├── 4028897_lineups.json
│   ├── 4028898.json
│   ├── 4028898_lineups.json
│   ├── 4028899.json
│   ├── 4028899_lineups.json
│   ├── 4028900.json
│   ├── 4028900_lineups.json
│   ├── 4028901.json
│   ├── 4028901_lineups.json
│   ├── 4028902.json
│   ├── 4028902_lineups.json
│   ├── 4028903.json
│   ├── 4028903_lineups.json
│   ├── 4028904.json
│   ├── 4028904_lineups.json
│   ├── 4028905.json
│   ├── 4028905_lineups.json
│   ├── 4028906.json
│   ├── 4028906_lineups.json
│   ├── 4028907.json
│   ├── 4028907_lineups.json
│   ├── 4028908.json
│   ├── 4028908_lineups.json
│   ├── 4028909.json
│   ├── 4028909_lineups.json
│   ├── 4028910.json
│   ├── 4028910_lineups.json
│   ├── 4028911.json
│   ├── 4028911_lineups.json
│   ├── 4028912.json
│   ├── 4028912_lineups.json
│   ├── 4028913.json
│   ├── 4028913_lineups.json
│   ├── 4028914.json
│   ├── 4028914_lineups.json
│   ├── 4028915.json
│   ├── 4028915_lineups.json
│   ├── 4028916.json
│   ├── 4028916_lineups.json
│   ├── 4028917.json
│   ├── 4028917_lineups.json
│   ├── 4028918.json
│   ├── 4028918_lineups.json
│   ├── 4028919.json
│   ├── 4028919_lineups.json
│   ├── 4028920.json
│   ├── 4028920_lineups.json
│   ├── 4028921.json
│   ├── 4028921_lineups.json
│   ├── 4028922.json
│   ├── 4028922_lineups.json
│   ├── 4028923.json
│   ├── 4028923_lineups.json
│   ├── 4028924.json
│   ├── 4028924_lineups.json
│   ├── 4028925.json
│   ├── 4028925_lineups.json
│   ├── 4028926.json
│   ├── 4028926_lineups.json
│   ├── 4028927.json
│   ├── 4028927_lineups.json
│   ├── 4028928.json
│   ├── 4028928_lineups.json
│   ├── 4028929.json
│   ├── 4028929_lineups.json
│   ├── 4028930.json
│   ├── 4028930_lineups.json
│   ├── 4028931.json
│   ├── 4028931_lineups.json
│   ├── 4028932.json
│   ├── 4028932_lineups.json
│   ├── 4028933.json
│   ├── 4028933_lineups.json
│   ├── 4028934.json
│   ├── 4028934_lineups.json
│   ├── 4028935.json
│   ├── 4028935_lineups.json
│   ├── 4028936.json
│   ├── 4028936_lineups.json
│   ├── 4028937.json
│   ├── 4028937_lineups.json
│   ├── 4028938.json
│   ├── 4028938_lineups.json
│   ├── 4028939.json
│   ├── 4028939_lineups.json
│   ├── 4028940.json
│   ├── 4028940_lineups.json
│   ├── 4028941.json
│   ├── 4028941_lineups.json
│   ├── 4028942.json
│   ├── 4028942_lineups.json
│   ├── 4028943.json
│   ├── 4028943_lineups.json
│   ├── 4028944.json
│   ├── 4028944_lineups.json
│   ├── 4028945.json
│   ├── 4028945_lineups.json
│   ├── 4028946.json
│   ├── 4028946_lineups.json
│   ├── 4028947.json
│   ├── 4028947_lineups.json
│   ├── 4028948.json
│   ├── 4028948_lineups.json
│   ├── 4028949.json
│   ├── 4028949_lineups.json
│   ├── 4028950.json
│   ├── 4028950_lineups.json
│   ├── 4028951.json
│   ├── 4028951_lineups.json
│   ├── 4028952.json
│   ├── 4028952_lineups.json
│   ├── 4028953.json
│   ├── 4028953_lineups.json
│   ├── 4028954.json
│   ├── 4028954_lineups.json
│   ├── 4028955.json
│   ├── 4028955_lineups.json
│   ├── 4028956.json
│   ├── 4028956_lineups.json
│   ├── 4028957.json
│   ├── 4028957_lineups.json
│   ├── 4028958.json
│   ├── 4028958_lineups.json
│   ├── 4028959.json
│   ├── 4028959_lineups.json
│   ├── 4028960.json
│   ├── 4028960_lineups.json
│   ├── 4028961.json
│   ├── 4028961_lineups.json
│   ├── 4028962.json
│   ├── 4028962_lineups.json
│   ├── 4028963.json
│   ├── 4028963_lineups.json
│   ├── 4028964.json
│   ├── 4028964_lineups.json
│   ├── 4028965.json
│   ├── 4028965_lineups.json
│   ├── 4028966.json
│   ├── 4028966_lineups.json
│   ├── 4028967.json
│   ├── 4028967_lineups.json
│   ├── 4028968.json
│   ├── 4028968_lineups.json
│   ├── 4028969.json
│   ├── 4028969_lineups.json
│   ├── 4028970.json
│   ├── 4028970_lineups.json
│   ├── 4028971.json
│   ├── 4028971_lineups.json
│   ├── 4028972.json
│   ├── 4028972_lineups.json
│   ├── 4028973.json
│   ├── 4028973_lineups.json
│   ├── 4028974.json
│   ├── 4028974_lineups.json
│   ├── 4028975.json
│   ├── 4028975_lineups.json
│   ├── 4028976.json
│   ├── 4028976_lineups.json
│   ├── 4028977.json
│   ├── 4028977_lineups.json
│   ├── 4028978.json
│   ├── 4028978_lineups.json
│   ├── 4028979.json
│   ├── 4028979_lineups.json
│   ├── 4028980.json
│   ├── 4028980_lineups.json
│   ├── 4028981.json
│   ├── 4028981_lineups.json
│   ├── 4028982.json
│   ├── 4028982_lineups.json
│   ├── 4028983.json
│   ├── 4028983_lineups.json
│   ├── 4028984.json
│   ├── 4028984_lineups.json
│   ├── 4028985.json
│   ├── 4028985_lineups.json
│   ├── 4028986.json
│   ├── 4028986_lineups.json
│   ├── 4028987.json
│   ├── 4028987_lineups.json
│   ├── 4031818.json
│   ├── 4031818_lineups.json
│   ├── documentation.pdf
│   └── league_phase.zip
├── uefa-cl-2025-2026-main.zip
└── wyscout
    ├── eventvideo
    │   ├── eventvideo.py
    │   ├── pyarmor_runtime_000000
    │   │   ├── __init__.py
    │   │   ├── py312
    │   │   │   ├── darwin_aarch64
    │   │   │   │   └── pyarmor_runtime.so
    │   │   │   ├── linux_aarch64
    │   │   │   │   └── pyarmor_runtime.so
    │   │   │   ├── linux_armv7
    │   │   │   │   └── pyarmor_runtime.so
    │   │   │   ├── linux_x86
    │   │   │   │   └── pyarmor_runtime.so
    │   │   │   ├── linux_x86_64
    │   │   │   │   └── pyarmor_runtime.so
    │   │   │   ├── windows_x86
    │   │   │   │   └── pyarmor_runtime.pyd
    │   │   │   └── windows_x86_64
    │   │   │       └── pyarmor_runtime.pyd
    │   │   ├── py313
    │   │   │   ├── darwin_aarch64
    │   │   │   │   └── pyarmor_runtime.so
    │   │   │   ├── linux_aarch64
    │   │   │   │   └── pyarmor_runtime.so
    │   │   │   ├── linux_armv7
    │   │   │   │   └── pyarmor_runtime.so
    │   │   │   ├── linux_x86
    │   │   │   │   └── pyarmor_runtime.so
    │   │   │   ├── linux_x86_64
    │   │   │   │   └── pyarmor_runtime.so
    │   │   │   ├── windows_x86
    │   │   │   │   └── pyarmor_runtime.pyd
    │   │   │   └── windows_x86_64
    │   │   │       └── pyarmor_runtime.pyd
    │   │   ├── py314
    │   │   │   ├── darwin_aarch64
    │   │   │   │   └── pyarmor_runtime.so
    │   │   │   ├── linux_aarch64
    │   │   │   │   └── pyarmor_runtime.so
    │   │   │   ├── linux_armv7
    │   │   │   │   └── pyarmor_runtime.so
    │   │   │   ├── linux_x86
    │   │   │   │   └── pyarmor_runtime.so
    │   │   │   ├── linux_x86_64
    │   │   │   │   └── pyarmor_runtime.so
    │   │   │   ├── windows_x86
    │   │   │   │   └── pyarmor_runtime.pyd
    │   │   │   └── windows_x86_64
    │   │   │       └── pyarmor_runtime.pyd
    │   │   └── __pycache__
    │   │       └── __init__.cpython-314.pyc
    │   └── README.md
    ├── eventvideo.zip
    └── __MACOSX
        └── eventvideo

32 directories, 320 files
```
