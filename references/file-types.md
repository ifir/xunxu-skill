# 文件分类规则

扩展名匹配不区分大小写。真实文件特征与扩展名冲突时，不执行或打开文件；根据有限文本内容能够明确判断的按内容归类，否则进入“其它”。

## 固定扩展名

- 文档资料：pdf、doc、docx、docm、dot、dotx、dotm、xls、xlsx、xlsm、xlsb、xlt、xltx、xltm、csv、tsv、ppt、pptx、pptm、pot、potx、potm、pps、ppsx、ppsm、odt、ods、odp、ott、ots、otp、rtf、txt、text、pages、numbers、key、wps、et、dps、hwp、hwpx、tex、ltx。
- 电子书：epub、mobi、azw、azw3、kf8、fb2、fb3、djvu、djv、chm、ibooks、lit、lrf、pdb、cbz、cbr、cb7、cbt、opf、ncx。
- 图片：jpg、jpeg、jpe、jfif、png、apng、gif、webp、heic、heif、avif、bmp、dib、tif、tiff、svg、svgz、ico、icns、jp2、j2k、jpf、jpx、jxl、tga、pcx、pnm、pbm、pgm、ppm、psd、psb、xcf、kra、ai、eps、dng、cr2、cr3、nef、nrw、arw、srf、sr2、raf、orf、rw2、pef、x3f、erf、mrw、raw。
- 视频：mp4、m4v、mov、qt、mkv、avi、wmv、flv、f4v、webm、mpeg、mpg、mpe、m2v、m2ts、mts、3gp、3g2、vob、ogv、rm、rmvb、asf、divx、dv。
- 音频：mp3、m4a、m4b、aac、wav、wave、flac、ogg、oga、opus、wma、aif、aiff、aifc、amr、ape、alac、ac3、dts、au、snd、ra、mid、midi、caf、cue。
- 字幕：srt、ass、ssa、vtt、sub、idx、smi、sami、sbv、ttml、dfxp、sup、usf、stl、lrc。
- 压缩包：zip、zipx、rar、7z、tar、gz、gzip、bz、bz2、bzip2、xz、zst、zstd、lz、lz4、lzh、lha、tgz、tbz、tbz2、txz、taz、cab、arj、ace、cpio、xar。
- 安装包：dmg、pkg、mpkg、app、exe、msi、msp、mst、msix、msixbundle、appx、appxbundle、apk、xapk、apks、aab、ipa、deb、rpm、appimage、snap、flatpak、flatpakref、flatpakrepo、run、bin、iso、crx、xpi、vsix、mobileconfig。
- 字体：ttf、otf、ttc、otc、woff、woff2、eot、pfa、pfb、afm、pfm、bdf、pcf、fon、fnt、suit、dfont。

## 代码

代码包括源码、脚本、Web 文件、数据库脚本、接口定义、模板、构建及基础设施配置、Notebook、IDE 工程和开发产物：

- C/C++/系统：c、h、cc、cpp、cxx、c++、hh、hpp、hxx、inl、ipp、tcc、m、mm、asm、s、inc、cu、cuh、rs、go、zig、d、di、v。
- JVM/.NET/移动：java、kt、kts、scala、sc、groovy、gvy、gy、gsh、cs、csx、fs、fsi、fsx、fsscript、vb、swift、dart。
- 脚本/科学：py、pyw、pyi、pyx、pxd、pxi、rb、rake、gemspec、php、phtml、php3、php4、php5、phps、pl、pm、pod、t、raku、rakumod、rakutest、lua、tcl、tk、awk、sed、sh、bash、zsh、fish、ksh、csh、ps1、psm1、psd1、bat、cmd、r、rmd、jl、mlx、sas、do、ado、mata。
- 函数式/其他语言：ex、exs、erl、hrl、gleam、hs、lhs、elm、ml、mli、re、rei、clj、cljs、cljc、bb、edn、lisp、lsp、cl、el、scm、ss、rkt、nim、nims、f、for、f77、f90、f95、f03、f08、fpp、vhd、vhdl、sv、svh、vh、sol、move、cairo、vy。
- Web/UI：html、htm、xhtml、css、scss、sass、less、styl、js、mjs、cjs、jsx、mts、cts、tsx、vue、svelte、astro。
- 数据库/接口/模板：sql、psql、graphql、gql、proto、thrift、avsc、fbs、capnp、prisma、openapi、jinja、jinja2、j2、mustache、hbs、handlebars、ejs、pug、jade、liquid、twig、erb、haml、slim。
- 构建/基础设施：mk、mak、cmake、gradle、sbt、tf、tfvars、tfstate、hcl、nomad、nix、dhall、rego、cue、bicep、pp。
- Notebook/工程/产物：ipynb、qmd、sln、suo、csproj、fsproj、vbproj、vcxproj、props、targets、proj、pbxproj、iml、ipr、iws、code-workspace、sublime-project、sublime-workspace、o、obj、a、lib、so、dylib、dll、pdb、bc、ll、wasm、class、jar、war、ear、pyc、pyo、whl、egg、gem、nupkg、crate、map、patch、diff、http、rest。

特殊开发文件名包括 Makefile、CMakeLists.txt、Dockerfile、Containerfile、Jenkinsfile、Vagrantfile、Gemfile、Rakefile、Procfile、Justfile、Taskfile.yml、Tiltfile、Brewfile、Podfile、Cartfile、BUILD、WORKSPACE、MODULE.bazel、meson.build、package.json、tsconfig.json、jsconfig.json、pom.xml、build.xml、composer.json、requirements.txt、Pipfile、pyproject.toml、Cargo.toml、Cargo.lock、go.mod、go.sum、docker-compose.yml 和 compose.yml。

## 歧义规则

- ts：MPEG-TS 文件特征归视频，TypeScript 文本特征归代码，否则归其它。
- m：含 Objective-C 指令归代码，否则归其它。
- md、markdown、rst、adoc、asciidoc：README、CHANGELOG、CONTRIBUTING、LICENSE、SECURITY 等开发文档或含明显开发内容时归代码；普通独立文档归文档资料。
- json、jsonc、json5、yaml、yml、toml、xml、ini、cfg、conf、properties、env、lock、rc：开发文件名、依赖/构建/部署字段或明显代码语境时归代码；普通导出数据、配置备份或无法确定时归其它。
- CSV/TSV 固定归文档资料。电子书、安装包等用途明确的容器格式优先于压缩包。jar 默认归代码。脚本后缀默认归代码。
- 无扩展名文件若以 shebang 开头则归代码；其余无法识别文件归其它。
- crdownload、part、download 是未完成下载，只跳过，不移动。
