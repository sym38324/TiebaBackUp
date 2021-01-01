import hashlib
import time
import const
import os
import sys
import shutil
import requests
import html
import traceback
import subprocess
import re
import json
from tqdm import tqdm
from download import DownloadPool
from avalon import Avalon

# Config
save_path = "./Backups/"  # 用于保存备份文件的路径，以 / 结尾
pids = [6887689380,7115748276,5550953900,6094744498,6674842204,6928885938,7152581963,5561830580,6288318252,6712727265,7084127359,5975838277,6299782345,6804800987,7090112615
]  # 帖子的pid列表
DirNames = ["", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""]  # 设置保存文件的目录名，与上述帖子一一对应。若留空 如 "" 则默认使用吧名-帖子标题（不推荐，通常系统对目录长度有限制）
lz = True  # 是否开启仅看楼主模式
comment = False  # 是否包括楼中楼（楼层评论）
OutputHTML = True  # 是否输出为 html？否则输出为 Markdown
overwrite = 2  # 1为跳过，2为默认覆盖
copy_to_website = 1  # 是否把备份好的文件拷贝到网站目录
website_dir = "/www/wwwroot/yoursite/target-dir/"  # “拷贝”的目标文件夹，注意末尾需要有 /
sckey = ""  # 用于server酱的消息推送,若不需要请保持现状
# 以下默认无需修改
const.PageUrl = "http://c.tieba.baidu.com/c/f/pb/page"
const.FloorUrl = "http://c.tieba.baidu.com/c/f/pb/floor"
const.EmotionUrl = "http://tieba.baidu.com/tb/editor/images/client/"
const.AliUrl = "https://tieba.baidu.com/tb/editor/images/ali/"
const.VoiceUrl = "http://c.tieba.baidu.com/c/p/voice?play_from=pb_voice_play&voice_md5="
const.SignKey = "tiebaclient!!!"


# const.IS_WIN=(os.name=="nt")

class RetryError(Exception):
    pass


class RetryExhausted(RetryError):
    pass


class RetryCheckFailed(RetryError):
    pass


class UserCancelled(Exception):
    pass


class TiebaApiError(Exception):
    pass


class UndifiedMsgType(TiebaApiError):
    pass


class RequestError(TiebaApiError):
    def __init__(self, data):
        self.data = data


class Tools(object):
    def __init__(self):
        pass

    @staticmethod
    def backup_existed_file():
        if os.path.exists(DirName):  # 备份一下本地已经爬到的文件
            Avalon.info("备份本地已经爬到的文件")
            try:
                os.rename(DirName, DirName + "-" + time.strftime("%Y%m%d-%Hh", time.localtime(int(time.time()))))
            except OSError:
                Avalon.info("备份文件已经存在")

    @staticmethod
    def delete_old_files():
        Avalon.info("删除3天以前的备份...")
        Dirname_backuped = DirName + "-" + time.strftime("%Y%m%d-%Hh", time.localtime(int(time.time()) - 86400 * 3))
        if os.path.exists(Dirname_backuped):
            Avalon.warning("检测到3天前的备份，删除ing...")
            shutil.rmtree(Dirname_backuped)
            Avalon.info("删除完毕")
        else:
            Avalon.warning("未发现3天前的备份，跳过")

    @staticmethod
    def copydir_overwrite(_from_path, _to_path):
        if os.path.exists(_from_path):
            if os.path.exists(_to_path):
                Avalon.warning("目标目录已存在，删除ing...")
                try:
                    shutil.rmtree(_to_path)
                except Exception as err1:
                    Avalon.error("删除目标文件失败，此次复制取消\n" + str(err1))
                    return 1
            try:
                shutil.copytree(_from_path, _to_path)
            except Exception as err2:
                Avalon.error("复制失败！\n" + str(err2))
            else:
                Avalon.info("复制成功")
        else:
            Avalon.warning("源目录不存在，跳过")

    @staticmethod
    def send_wxmsg(_sckey, _title="标题", _context="正文"):
        url = "https://sc.ftqq.com/%s.send" % _sckey
        _context = _context + "     \n\n" + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        data = {
            "text": "%s" % _title,
            "desp": "%s" % _context
        }
        try:
            res = requests.post(url=url, data=data)
            msg_back = json.loads(res.text)
            if msg_back["errmsg"] == "success":
                Avalon.info("返回值：%s" % (msg_back["errmsg"]))
            else:
                Avalon.warning("返回值：%s" % (msg_back["errmsg"]))
        except Exception:
            Avalon.error("消息发送错误")


def MakeDir(dirname):
    dirname = save_path + dirname
    global IsCreate
    if dirname in IsCreate:
        return
    if os.path.isdir(dirname):
        pass
    elif os.path.exists(dirname):
        raise OSError("%s is a file" % dirname)
    else:
        os.makedirs(dirname)
    IsCreate.add(dirname)


def Init(pid, overwrite, _DirName):
    global FileHandle, Progress, AudioCount, VideoCount, ImageCount, \
        Pool, IsDownload, IsCreate, OutputHTML, FFmpeg
    IsDownload = set()
    IsCreate = set()
    AudioCount = VideoCount = ImageCount = 0
    DirName = save_path + _DirName
    if os.path.isdir(DirName):
        Avalon.warning("\"%s\"已存在" % DirName)
        if overwrite == 1:
            Avalon.warning("跳过%d" % pid)
        elif overwrite == 2:
            Avalon.warning("默认覆盖\"%s\"" % DirName)
        elif not Avalon.ask("是否覆盖?", False):
            raise UserCancelled("...")
    elif os.path.exists(DirName):
        raise OSError("存在同名文件")
    else:
        os.makedirs(DirName)
    if OutputHTML:
        FileHandle = open("%s/%d.html" % (DirName, pid), "w", encoding="utf-8")
        Write('<!doctype html><html lang="zh-cn"><head><link rel="stylesheet"'
              ' type="text/css" href="main.css"><title>一个备份站...%d</title><link rel="shortcut icon" href="favicon.ico"></head><body><div id="write">' % pid)
        shutil.copy("./resources/main.css", DirName + "/")
        shutil.copy("./resources/favicon.ico", DirName + "/")
    else:
        FileHandle = open("%s/%d.md" % (DirName, pid), "w", encoding="utf-8")
    try:
        subprocess.Popen("ffmpeg", stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL).wait()
        FFmpeg = 1
    except FileNotFoundError:
        Avalon.warning("未找到ffmpeg,语音将不会被转为mp3")
        FFmpeg = 0
    Pool = DownloadPool(DirName + "/", "file")
    Progress = tqdm(unit="floor")


def ConvertAudio(_DirName):
    global AudioCount, FFmpeg
    DirName = save_path + _DirName
    if (not FFmpeg) or (not AudioCount):
        return
    for i in tqdm(range(1, AudioCount + 1), unit="audio", ascii=True):
        if FFmpeg:
            prefix = "%s/audios/%d" % (DirName, i)
            subprocess.Popen(["ffmpeg", "-i", "%s.amr" % prefix,
                              "%s.mp3" % prefix, "-y"], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL).wait()
            os.remove("%s.amr" % prefix)


def Done():
    global OutputHTML
    if OutputHTML:
        Write('</div></body></html>')
    FileHandle.close()
    Progress.set_description("Waiting for the download thread...")
    err_status = Pool.Stop()
    Progress.close()
    if err_status != 0:
        write_err_info()
    return


def write_err_info():
    with open(save_path + "errors.txt", "a", encoding="utf-8") as f_err_info:
        f_err_info.writelines("https://tieba.baidu.com/p/" + str(pid) + "\n")
    Avalon.error(f"帖子 {pid} 可能出错, 帖子id已保存至 {save_path}errors.txt")


def ForceStop():
    if "FileHandle" in globals().keys():
        FileHandle.close()
    if "Pool" in globals().keys():
        Pool.ImgProc.close()
    if "Progress" in globals().keys():
        Progress.close()


def CallFunc(func=None, args=None, kwargs=None):
    if not (func is None):
        if args is None:
            if kwargs is None:
                return func()
            else:
                return func(**kwargs)
        else:
            if kwargs is None:
                return func(*args)
            else:
                return func(*args, **kwargs)


# times == -1 ---> forever


def Retry(func, args=None, kwargs=None, cfunc=None, ffunc=None, fargs=None, fkwargs=None, times=3, sleep=1):
    fg = 0
    while times:
        try:
            resp = CallFunc(func, args, kwargs)
        except Exception:
            CallFunc(ffunc, fargs, fkwargs)
            times = max(-1, times - 1)
            time.sleep(sleep)
        else:
            if CallFunc(cfunc, (resp,)) in [None, True]:
                return resp
            times = max(-1, times - 1)
            fg = 1
    if fg:
        raise RetryCheckFailed(func.__qualname__, args, cfunc.__qualname__, resp)
    else:
        raise RetryExhausted(func.__qualname__, args, cfunc.__qualname__)


def Write(content):
    FileHandle.write(content)


def SignRequest(data):
    s = ""
    keys = sorted(data.keys())
    for i in keys:
        s += i + "=" + data[i]
    sign = hashlib.md5((s + const.SignKey).encode("utf-8")).hexdigest().upper()
    data.update({"sign": str(sign)})
    return data


def TiebaRequest(url, data, first=False):
    if first:
        req = Retry(requests.post, args=(url,), kwargs={"data": SignRequest(data)},
                    cfunc=(lambda x: x.status_code == 200), ffunc=print,
                    fargs=("Connect Failed,Retrying...\n",), times=5)
    else:
        req = Retry(requests.post, args=(url,), kwargs={"data": SignRequest(data)},
                    cfunc=(lambda x: x.status_code == 200), ffunc=Progress.set_description,
                    fargs=("Connect Failed,Retrying...",), times=5)
    req.encoding = 'utf-8'
    ret = req.json()
    if int(ret["error_code"]) != 0:
        raise RequestError({"code": int(ret["error_code"]), "msg": str(ret["error_msg"])})
    return req.json()


def ReqContent(pid, fid, lz):
    if ~fid:
        return TiebaRequest(const.PageUrl,
                            {"kz": str(pid), "pid": str(fid), "lz": str(int(lz)), "_client_version": "9.9.8.32"})
    else:
        return TiebaRequest(const.PageUrl, {"kz": str(pid), "lz": str(int(lz)), "_client_version": "9.9.8.32"})


def ReqComment(pid, fid, pn):
    return TiebaRequest(const.FloorUrl, {"kz": str(pid), "pid": str(fid), "pn": str(pn), "_client_version": "9.9.8.32"})


def FormatTime(t):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(int(t)))


def ProcessText(text, in_comment):
    global OutputHTML
    if OutputHTML:
        if in_comment:
            return html.escape(text)
        else:
            return html.escape(text).replace("\n", "<br />")
    else:
        if in_comment:
            return html.escape(text)
        else:
            return html.escape(text).replace("\\", "\\\\").replace("\n", "  \n").replace("*", "\\*") \
                .replace("-", "\\-").replace("_", "\\_").replace("(", "\\(").replace(")", "\\)") \
                .replace("#", "\\#").replace("`", "\\`").replace("~", "\\~").replace("[", "\\[") \
                .replace("]", "\\]").replace("!", "\\!").replace(".", "\\.").replace("+", "\\+")


def ProcessUrl(url, text):
    return '<a href="%s">%s</a>' % (url, text)


def ProcessImg(url):
    global ImageCount, DirName
    if url[0:2] == "//":
        url = "http:" + url
    MakeDir(DirName + "/images")
    ImageCount += 1
    name = "images/%d.%s" % (ImageCount, url.split("?")[0].split(".")[-1])
    Pool.Download(url, name)
    return '\n<div><img src="%s" /></div>\n' % name


def ProcessVideo(url, cover):
    global VideoCount, DirName, OutputHTML
    MakeDir(DirName + "/videos")
    VideoCount += 1
    vname = "videos/%d.%s" % (VideoCount, url.split(".")[-1])
    cname = "videos/%d_cover.%s" % (VideoCount, cover.split(".")[-1])
    Pool.Download(url, vname)
    Pool.Download(cover, cname)
    if OutputHTML:
        return '\n<video src="%s" poster="%s" controls />\n' % (vname, cname)
    else:
        return '\n<a href="%s"><img src="%s" title="点击查看视频"></a>\n' % (vname, cname)


def ProcessQuoteVideo(url):
    return '\n<a href="%s">点击查看外链视频</a>\n' % url

def ProcessAudio(md5):
    global AudioCount, DirName, OutputHTML, FFmpeg
    MakeDir(DirName + "/audios")
    AudioCount += 1
    Pool.Download(const.VoiceUrl + md5, "audios/%d.amr" % AudioCount)
    if OutputHTML and FFmpeg:
        return '<audio src="audios/%d.mp3" controls />' % AudioCount
    elif FFmpeg:
        return '<a href="audios/%d.mp3">语音</a>\n' % AudioCount
    else:
        return '<a href="audios/%d.amr">语音</a>\n' % AudioCount


def ProcessEmotion(floor, name, text):
    global DirName, IsDownload
    MakeDir(DirName + "/images")
    lname = len(name)
    if name == "image_emoticon":
        name += "1"
        lname += 1
    url = ""
    if lname >= 3 and name[0:3] == "ali":
        url = "%s%s.gif" % (const.AliUrl, name)
        name += ".gif"
    elif lname >= 14 and name[0:14] == "image_emoticon":
        url = "%s%s.png" % (const.EmotionUrl, name)
        name += ".png"
    else:
        Avalon.warning("第%s楼出现未知表情:%s\n" % (floor, name), front="\n")
        return ''
    if name not in IsDownload:
        IsDownload.add(name)
        Pool.Download(url, "images/%s" % name)
    return '<img src="images/%s" alt="%s" title="%s" />' % (name, text, text)


def ProcessContent(floor, data, in_comment):
    content = ""
    for s in data:
        try:
            if str(s["type"]) == "0":
                content += ProcessText(s["text"], in_comment)
            elif str(s["type"]) == "1":
                content += ProcessUrl(s["link"], s["text"])
            elif str(s["type"]) == "2":
                content += ProcessEmotion(floor, s["text"], s["c"])
            elif str(s["type"]) == "3":
                content += ProcessImg(s["origin_src"])
            elif str(s["type"]) == "4":
                content += ProcessText(s["text"], in_comment)
            elif str(s["type"]) == "5":
                try:
                    content += ProcessVideo(s["link"], s["src"])
                except KeyError:
                    content += ProcessQuoteVideo(s["text"])
            elif str(s["type"]) == "9":
                content += ProcessText(s["text"], in_comment)
            elif str(s["type"]) == "10":
                content += ProcessAudio(s["voice_md5"])
            elif str(s["type"]) == "11":
                content += ProcessImg(s["static"])
            elif str(s["type"]) == "20":
                content += ProcessImg(s["src"])
            else:
                Avalon.warning("floor %s: content data wrong: \n%s\n" % (floor, str(s)), front="\n")
                # raise UndifiedMsgType("content data wrong: \n%s\n"%str(s))
        except KeyError:
            write_err_info()
            Avalon.error("KeyError! 建议修改源码中字典的Key\n" + traceback.format_exc(), front="\n")
            content += '\n<a>[Error] 这里似乎出错了...类型 KeyError</a>\n'
        except Exception:
            write_err_info()
            Avalon.error("发生异常:\n" + traceback.format_exc(), front="\n")
            content += '\n<a>[Error] 这里似乎出错了...</a>\n'
        else:
            return content


def ProcessFloor(floor, author, t, content):
    global OutputHTML
    if OutputHTML:
        return '<hr />\n<div>%s</div><br />\n<div class="author">\
            %s楼 | %s | %s</div>\n' % (content, floor, author, FormatTime(t))
    else:
        return '<hr />\n\n%s\n<div align="right" style="font-size:12px;color:#CCC;">\
            %s楼 | %s | %s</div>\n' % (content, floor, author, FormatTime(t))


def ProcessComment(author, t, content):
    return '%s | %s:<blockquote>%s</blockquote>' % (FormatTime(t), author, content)


def GetComment(floor, pid, fid):
    global OutputHTML
    if OutputHTML:
        Write('<pre>')
    else:
        Write('<pre style="background-color: #f6f8fa;border-radius: 3px;\
            font-size: 85%;line-height: 1.45;overflow: auto;padding: 16px;">')
    pn = 1
    while 1:
        data = ReqComment(pid, fid, pn)
        data = data["subpost_list"]
        if len(data) == 0:
            break
        for comment in data:
            Write(ProcessComment(comment["author"]["name_show"], comment["time"],
                                 ProcessContent(floor, comment["content"], 1)))
        pn += 1
    Write('</pre>')


def ProcessUserList(data):
    userlist = {}
    for user in data:
        userlist[user["id"]] = {"id": user["portrait"].split("?")[0], "name": user["name_show"]}
    return userlist


def GetTitle(pid):
    data = TiebaRequest(const.PageUrl, {"kz": str(pid), "_client_version": "9.9.8.32"}, True)
    return {"post": data["post_list"][0]["title"], "forum": data["forum"]["name"]}


def GetPost(pid, lz, comment):
    lastfid = -1
    while 1:
        data = ReqContent(pid, lastfid, lz)
        # print(data)
        userlist = ProcessUserList(data["user_list"])
        for floor in data["post_list"]:
            if int(floor["id"]) == lastfid:
                continue
            fnum = floor["floor"]
            Progress.update(1)
            Progress.set_description("Collecting floor %s" % fnum)
            fid = int(floor["id"])
            Write(ProcessFloor(fnum, userlist[floor["author_id"]]["name"], floor["time"],
                               ProcessContent(fnum, floor["content"], 0)))
            if int(floor["sub_post_number"]) == 0:
                continue
            if comment:
                GetComment(fnum, pid, floor["id"])
        if lastfid == fid:
            break
        # print(fid,lastfid)
        lastfid = fid


def customized_tools():
    #  以下--删除3天以前的备份
    Tools.delete_old_files()
    #  以下--复制文件到网站目录
    if copy_to_website == 1:
        Avalon.info("准备复制文件到网站目录----")
        Tools.copydir_overwrite(_from_path="./%s" % DirName, _to_path=website_dir + DirName)
    elif copy_to_website == 0:
        Avalon.info("跳过 复制文件到网站目录")
    #  以下--向server酱推送消息
    if not sckey == "":
        Avalon.info("尝试向Server酱推送消息……")
        Tools.send_wxmsg(_sckey=sckey, _title="贴吧备份（全部楼层）", _context="今日份的备份已完成...\n\n一切顺利..Maybe..\n\n帖子id：%d" % pid)
    else:
        Avalon.warning("SCKEY为空，跳过微信推送")


if __name__ == '__main__':
    os.chdir(sys.path[0])  # 切换至脚本文件所在目录
    DirName_flag = 0
    for pid in pids:
        try:
            Avalon.info("当前时间: " + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(time.time()))))
            Avalon.info("帖子id: %d" % pid)
            title = GetTitle(pid)
            title["forum"] = re.sub(r"[\/\\\:\*\?\"\<\>\|]", "_", title["forum"])
            title["post"] = re.sub(r"[\/\\\:\*\?\"\<\>\|]", "_", title["post"])
            #  lz = Avalon.ask("只看楼主?", False)
            Avalon.info("只看楼主: " + str(lz))
            #  comment = (0 if lz else Avalon.ask("包括评论?", True))
            Avalon.info("包括评论: " + str(comment))
            #  DirName = Avalon.gets("文件夹名(空则表示使用\"吧名-标题\"):")
            DirName = DirNames[DirName_flag]
            Avalon.info("目录名: " + DirName)
            Tools.backup_existed_file()  # 备份已爬取的文件
            #  OutputHTML = Avalon.ask("输出HTML(否则表示输出Makrdown)?:", True)
            Avalon.info("输出为Html: " + str(OutputHTML))
            if len(DirName) == 0:
                DirName = title["forum"] + "-" + title["post"]
                DirName = re.sub(r'(/|\\|\?|\||\*|\:|\"|\<|\>|\.)', '', DirName)  # 去除不能当文件夹名的字符
            Avalon.info("id: %d , 选定: %s && %s评论 , 目录: \"%s\"" % (
                pid, ("楼主" if lz else "全部"), ("全" if comment else "无"), DirName))
            Init(pid, overwrite, DirName)
            GetPost(pid, lz, comment)
            Done()
            ConvertAudio(DirName)
        except KeyboardInterrupt:
            ForceStop()
            Avalon.error("Raised Control-C", front="\n")
            write_err_info()
            t_in = Avalon.gets("请选择：1.退出程序  2.退出当前帖子\n", front="\n")
            if "1" in t_in:
                exit(0)
            elif "2" in t_in:
                continue
            else:
                continue
        except UserCancelled:
            Avalon.warning("用户取消")
        except RequestError as err:
            err = err.data
            Avalon.error("百度贴吧API返回错误,代码:%d\n描述:%s" % (err["code"], err["msg"]), front="\n")
        except Exception:
            ForceStop()
            Avalon.error("发生异常:\n" + traceback.format_exc(), front="\n")
            exit(0)
        else:
            customized_tools()  # 运行自定义工具
            Avalon.info("完成 %d" % pid)
        try:
            if pids.index(pid) < len(pids) - 1:
                Avalon.info("10s后进行下一个帖子...\n", front="\n\n")
                time.sleep(10)
                DirName_flag = DirName_flag + 1
            else:
                Avalon.info("全部帖子已经备份完成！", front="\n\n")
        except KeyboardInterrupt:
            Avalon.error("Control-C,exiting", front="\n")
            exit(0)
