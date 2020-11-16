# ctrans.py
---------

very crude source code comment translator. powered by google translate.

currently handles C-style and scripting-style (i.e. '#') comments; note that
comments formatted as '### comment' will still end up as '# comment', this
is a bug i don't care about fixing atm; i'm more concerned with just getting
this working.

## PREREQUISITE

### Setup Cloud Console project and download credentials
> https://cloud.google.com/translate/docs/basic/setup-basic

### Set path to credentials:
> GOOGLE_APPLICATION_CREDENTIALS={path_to_credential}

### Install packages

> pip install chardet simplejson google-cloud-translate

## USAGE:

    ctrans.py -s <filename>
    translates a single file

    ctrans.py -d <dir>
    translates all source files in a directory
    
    other flags:
        -e                  set input file encoding
        -o                  set output file encoding
        -t                  set trace (debugging output)
        --keep_source       keep source texts
        --string_literals   translate string literals
        --lang={langid} set target lanauge (default: en)

## SUPPORTED

### c-styles
.c, .cpp, .cc, .h. hpp, .js, .ts
### lua
.lua
### scripts
.py, .pl, .rb
        
## EXAMPLES

#### Original Source code 

```C
/* Это тестовый файл источник */

#include <file1.h>
#include <file2.h>

// больше кода

int foo() {
    const char* test1 = "Объяснение";
    const char* test2 = "это дело 1";

    /*
     * Объяснение
     * это дело 1
     * и вещь 2
     */

     func();
     return 0;
}

/* Объяснени е */
```

#### Translated

> ctrans -s test.c

```C
/*This is a test file source*/

#include <file1.h>
#include <file2.h>

// more code

int foo() {
    const char* test1 = "Объяснение";
    const char* test2 = "это дело 1";

    /*
* Explanation
* this case 1
* and item 2
     */

     func();
     return 0;
}

/*It is explained*/
```


#### Translated with original text and also string literals too

> ctrans -s test.c --keep_source --string_literals

```C
/* Это тестовый файл источник (This is a test file source)*/

#include <file1.h>
#include <file2.h>

// больше кода(more code)

int foo() {
    const char* test1 = "Объяснение(Explanation)";
    const char* test2 = "это дело 1(this case 1)";

    /*
     * Объяснение(* Explanation)
     * это дело 1(* this case 1)
     * и вещь 2(* and item 2)
     */

     func();
     return 0;
}

/* Объяснени е (It is explained)*/
```

## DECODE/ENCODE NOTES:

the default encoding and decoding is utf-8. specifying 'auto' for the
decoding will attempt to guess the file's encoding. this is at best a guess,
and at worst completely wrong.

encoding is not a trivial matter, and there are a million ways a file might
be encoded. 

## TODO:

    * lots
    
