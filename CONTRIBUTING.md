# Contributing to WeeViewer

感谢你对WeeViewer的关注！我们欢迎任何形式的贡献。

## 如何贡献

### 报告问题

如果你发现了bug或有功能建议，请：

1. 检查[Issues](https://github.com/soloverr/WeeViewer/issues)确保问题未被报告
2. 使用问题模板创建新的Issue
3. 提供详细的问题描述和复现步骤

### 提交代码

#### 开发环境设置

1. Fork仓库到你的GitHub账户
2. Clone你的fork：
```bash
git clone https://github.com/your-username/WeeViewer.git
cd WeeViewer
```

3. 安装依赖：
```bash
pip install -r requirements.txt
```

4. 运行程序：
```bash
python src/weeviewer/main.py
```

#### 创建功能分支

```bash
git checkout -b feature/your-feature-name
# 或
git checkout -b fix/your-bug-fix
```

#### 进行修改

- 遵循现有代码风格
- 添加必要的注释
- 确保代码可运行

#### 测试

```bash
# 运行测试
pytest

# 类型检查
mypy .
```

#### 提交更改

```bash
git add .
git commit -m "type(scope): brief description"
```

提交信息格式：
- `feat`: 新功能
- `fix`: Bug修复
- `docs`: 文档更新
- `style`: 代码格式（不影响功能）
- `refactor`: 重构
- `test`: 测试相关
- `chore`: 构建过程或工具变更

示例：
```
feat(theme): add dark mode support
fix(search): handle special characters in regex
docs(readme): update installation instructions
```

#### 推送并创建Pull Request

```bash
git push origin feature/branch-name
```

然后在GitHub上创建Pull Request。

## 代码规范

### Python代码

- 遵循PEP 8规范
- 使用有意义的变量和函数名
- 添加docstring说明函数用途
- 保持函数简短，单一职责

### Git提交

- 提交信息简洁明了
- 一个提交只做一件事
- 不要提交敏感信息

## Pull Request流程

1. 确保你的代码与main分支同步
2. 运行测试确保没有破坏现有功能
3. 更新相关文档
4. 清理不必要的代码和注释
5. 创建Pull Request并填写模板
6. 等待审查和反馈

## 审查标准

- 代码质量和可读性
- 测试覆盖率
- 文档完整性
- 与项目目标一致

## 行为准则

- 尊重所有贡献者
- 建设性讨论
- 欢迎新手提问
- 保持友好和专业

## 获取帮助

如果你有任何问题，可以：
- 查看[README.md](README.md)
- 搜索现有Issues
- 创建新的Issue提问

## 发布流程

版本发布遵循语义化版本：
- 主版本号：不兼容的API修改
- 次版本号：向下兼容的功能性新增
- 修订号：向下兼容的问题修正

再次感谢你的贡献！🎉