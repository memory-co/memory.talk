# 本轮目标

1. stories/claude_code_import.md 里面的东西有点旧了，参考前面几轮的迭代改动，将这里的字段更新，同时将集成测试中的代码也更新。

2. 集成测试导入数据的时候，请使用connector中的脚本进行导入。

3. subject增加match字段 和 优先级字段，他可以用这个字段来判断，哪些platform & role 的属于这个subject。使用 jinja2 的 expression 作为 expression。这个match在什么时生效？就是导入的时候判断，导入完之后就不再判断了。
