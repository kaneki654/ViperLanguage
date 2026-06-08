" Vim syntax file for Viper (.vp)
" Keep keyword/builtin lists in sync with viper/keywords.py
if exists("b:current_syntax")
  finish
endif

" Statement / control keywords
syn keyword viperKeyword let fn if elif else while for in match case
syn keyword viperKeyword return break continue pass import from spawn

" Operator-like keywords
syn keyword viperOperatorWord and or not is

" Constants
syn keyword viperBoolean True False
syn keyword viperConstant None

" Builtins (mirror BUILTINS in viper/keywords.py)
syn keyword viperBuiltin print len range int float str bool list dict
syn keyword viperBuiltin set tuple sum min max abs sorted enumerate zip
syn keyword viperBuiltin map filter input round type repr

" Literals
syn match viperNumber "\<\d\+\(\.\d\+\)\?\>"
syn region viperString start=+"+ skip=+\\"+ end=+"+

" The pipe operator
syn match viperOperator "|>"

hi def link viperKeyword       Keyword
hi def link viperOperatorWord  Operator
hi def link viperOperator      Operator
hi def link viperBoolean       Boolean
hi def link viperConstant      Constant
hi def link viperBuiltin       Function
hi def link viperNumber        Number
hi def link viperString        String

let b:current_syntax = "viper"
