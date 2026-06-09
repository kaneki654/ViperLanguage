" Vim syntax file for Viper (.vp)
" Keep keyword/builtin lists in sync with viper/keywords.py
if exists("b:current_syntax")
  finish
endif

syn keyword viperKeyword let fn if elif else while for in match case
syn keyword viperKeyword return break continue pass import from spawn
syn keyword viperKeyword class try except finally raise del as
syn keyword viperKeyword with assert global nonlocal

syn keyword viperOperatorWord and or not is

syn keyword viperBoolean True False
syn keyword viperConstant None

syn keyword viperBuiltin print len range int float str bool list dict
syn keyword viperBuiltin set tuple sum min max abs sorted enumerate zip
syn keyword viperBuiltin map filter input round type repr isinstance super
syn keyword viperBuiltin pp read_file write_file clamp

syn match viperNumber "\<\d\+\(\.\d\+\)\?\>"
syn region viperString start=+"+ skip=+\\"+ end=+"+
syn region viperFString start=+f"+ skip=+\\"+ end=+"+

syn match viperOperator "|>"
syn match viperOperator ":="

hi def link viperKeyword       Keyword
hi def link viperOperatorWord  Operator
hi def link viperOperator      Operator
hi def link viperBoolean       Boolean
hi def link viperConstant      Constant
hi def link viperBuiltin       Function
hi def link viperNumber        Number
hi def link viperString        String
hi def link viperFString       String

let b:current_syntax = "viper"

