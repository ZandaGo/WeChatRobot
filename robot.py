# -*- coding: utf-8 -*-

import logging
import re
import time
import xml.etree.ElementTree as ET
from queue import Empty
from threading import Thread

from IPython.core.events import pre_run_cell

from base.func_zhipu import ZhiPu

from wcferry import Wcf, WxMsg

from base.func_bard import BardAssistant
from base.func_chatglm import ChatGLM
from base.func_chatgpt import ChatGPT
from base.func_chengyu import cy
from base.func_news import News
from base.func_tigerbot import TigerBot
from base.func_xinghuo_web import XinghuoWeb
from configuration import Config
from constants import ChatType
from job_mgmt import Job

import img_ocr
from datetime import datetime

__version__ = "39.2.4.0"


class Robot(Job):
    """个性化自己的机器人
    """

    def __init__(self, config: Config, wcf: Wcf, chat_type: int) -> None:
        self.wcf = wcf
        self.config = config
        self.LOG = logging.getLogger("Robot")
        self.wxid = self.wcf.get_self_wxid()
        self.allContacts = self.getAllContacts()

        if ChatType.is_in_chat_types(chat_type):
            if chat_type == ChatType.TIGER_BOT.value and TigerBot.value_check(self.config.TIGERBOT):
                self.chat = TigerBot(self.config.TIGERBOT)
            elif chat_type == ChatType.CHATGPT.value and ChatGPT.value_check(self.config.CHATGPT):
                self.chat = ChatGPT(self.config.CHATGPT)
            elif chat_type == ChatType.XINGHUO_WEB.value and XinghuoWeb.value_check(self.config.XINGHUO_WEB):
                self.chat = XinghuoWeb(self.config.XINGHUO_WEB)
            elif chat_type == ChatType.CHATGLM.value and ChatGLM.value_check(self.config.CHATGLM):
                self.chat = ChatGLM(self.config.CHATGLM)
            elif chat_type == ChatType.BardAssistant.value and BardAssistant.value_check(self.config.BardAssistant):
                self.chat = BardAssistant(self.config.BardAssistant)
            elif chat_type == ChatType.ZhiPu.value and ZhiPu.value_check(self.config.ZhiPu):
                self.chat = ZhiPu(self.config.ZhiPu)
            else:
                self.LOG.warning("未配置模型")
                self.chat = None
        else:
            if TigerBot.value_check(self.config.TIGERBOT):
                self.chat = TigerBot(self.config.TIGERBOT)
            elif ChatGPT.value_check(self.config.CHATGPT):
                self.chat = ChatGPT(self.config.CHATGPT)
            elif XinghuoWeb.value_check(self.config.XINGHUO_WEB):
                self.chat = XinghuoWeb(self.config.XINGHUO_WEB)
            elif ChatGLM.value_check(self.config.CHATGLM):
                self.chat = ChatGLM(self.config.CHATGLM)
            elif BardAssistant.value_check(self.config.BardAssistant):
                self.chat = BardAssistant(self.config.BardAssistant)
            elif ZhiPu.value_check(self.config.ZhiPu):
                self.chat = ZhiPu(self.config.ZhiPu)
            else:
                self.LOG.warning("未配置模型")
                self.chat = None

        self.LOG.info(f"已选择: {self.chat}")

    @staticmethod
    def value_check(args: dict) -> bool:
        if args:
            return all(value is not None for key, value in args.items() if key != 'proxy')
        return False

    def toAt(self, msg: WxMsg) -> bool:
        """处理被 @ 消息
        :param msg: 微信消息结构
        :return: 处理状态，`True` 成功，`False` 失败
        """
        return self.toChitchat(msg)

    def toChengyu(self, msg: WxMsg) -> bool:
        """
        处理成语查询/接龙消息
        :param msg: 微信消息结构
        :return: 处理状态，`True` 成功，`False` 失败
        """
        status = False
        texts = re.findall(r"^([#|?|？])(.*)$", msg.content)
        # [('#', '天天向上')]
        if texts:
            flag = texts[0][0]
            text = texts[0][1]
            if flag == "#":  # 接龙
                if cy.isChengyu(text):
                    rsp = cy.getNext(text)
                    if rsp:
                        self.sendTextMsg(rsp, msg.roomid)
                        status = True
            elif flag in ["?", "？"]:  # 查词
                if cy.isChengyu(text):
                    rsp = cy.getMeaning(text)
                    if rsp:
                        self.sendTextMsg(rsp, msg.roomid)
                        status = True

        return status

    def toChitchat(self, msg: WxMsg) -> bool:
        """闲聊，接入 ChatGPT
        """
        rsp = "我是机器人，请不要@我"
        # if not self.chat:  # 没接 ChatGPT，固定回复
        #     rsp = "我是机器人，请不要@我"
        # else:  # 接了 ChatGPT，智能回复
        #     q = re.sub(r"@.*?[\u2005|\s]", "", msg.content).replace(" ", "")
        #     rsp = self.chat.get_answer(q, (msg.roomid if msg.from_group() else msg.sender))
        #
        if rsp:
            if msg.from_group():
                self.sendTextMsg(rsp, msg.roomid, msg.sender)
            # else:
            #     self.sendTextMsg(rsp, msg.sender)

            return True
        else:
            self.LOG.error(f"无法从 ChatGPT 获得答案")
            return False

    def processMsg(self, msg: WxMsg) -> None:
        """当接收到消息的时候，会调用本方法。如果不实现本方法，则打印原始消息。
        此处可进行自定义发送的内容,如通过 msg.content 关键字自动获取当前天气信息，并发送到对应的群组@发送者
        群号：msg.roomid  微信ID：msg.sender  消息内容：msg.content
        content = "xx天气信息为："
        receivers = msg.roomid
        self.sendTextMsg(content, receivers, msg.sender)
        """

        # 群聊消息
        if msg.from_group():
            # 如果在群里被 @
            if msg.roomid not in self.config.GROUPS:  # 不在配置的响应的群列表里，忽略
                return

            if msg.roomid in self.config.GROUPS:
                self.toImageChat(msg)

            if msg.is_at(self.wxid):  # 被@
                self.toAt(msg)

            else:  # 其他消息
                self.toChengyu(msg)

            return  # 处理完群聊信息，后面就不需要处理了

        # 非群聊信息，按消息类型进行处理
        if msg.type == 37:  # 好友请求
            self.autoAcceptFriendRequest(msg)

        elif msg.type == 10000:  # 系统信息
            self.sayHiToNewFriend(msg)

        elif msg.type == 0x01:  # 文本消息
            # 让配置加载更灵活，自己可以更新配置。也可以利用定时任务更新。
            if msg.from_self():
                if msg.content == "^更新$":
                    self.config.reload()
                    self.LOG.info("已更新")
            else:
                self.toChitchat(msg)  # 闲聊

    def onMsg(self, msg: WxMsg) -> int:
        try:
            self.LOG.info(msg)  # 打印信息
            self.processMsg(msg)
        except Exception as e:
            self.LOG.error(e)

        return 0

    def enableRecvMsg(self) -> None:
        self.wcf.enable_recv_msg(self.onMsg)

    def enableReceivingMsg(self) -> None:
        def innerProcessMsg(wcf: Wcf):
            while wcf.is_receiving_msg():
                try:
                    msg = wcf.get_msg()
                    self.LOG.info(msg)
                    self.processMsg(msg)
                except Empty:
                    continue  # Empty message
                except Exception as e:
                    self.LOG.error(f"Receiving message error: {e}")

        self.wcf.enable_receiving_msg()
        Thread(target=innerProcessMsg, name="GetMessage", args=(self.wcf,), daemon=True).start()

    def sendTextMsg(self, msg: str, receiver: str, at_list: str = "") -> None:
        """ 发送消息
        :param msg: 消息字符串
        :param receiver: 接收人wxid或者群id
        :param at_list: 要@的wxid, @所有人的wxid为：notify@all
        """
        # msg 中需要有 @ 名单中一样数量的 @
        ats = ""
        if at_list:
            if at_list == "notify@all":  # @所有人
                ats = " @所有人"
            else:
                wxids = at_list.split(",")
                for wxid in wxids:
                    # 根据 wxid 查找群昵称
                    ats += f" @{self.wcf.get_alias_in_chatroom(wxid, receiver)}"

        # {msg}{ats} 表示要发送的消息内容后面紧跟@，例如 北京天气情况为：xxx @张三
        if ats == "":
            self.LOG.info(f"To {receiver}: {msg}")
            self.wcf.send_text(f"{msg}", receiver, at_list)
        else:
            self.LOG.info(f"To {receiver}: {ats}\r{msg}")
            self.wcf.send_text(f"{ats}\n\n{msg}", receiver, at_list)

    def getAllContacts(self) -> dict:
        """
        获取联系人（包括好友、公众号、服务号、群成员……）
        格式: {"wxid": "NickName"}
        """
        contacts = self.wcf.query_sql("MicroMsg.db", "SELECT UserName, NickName FROM Contact;")
        return {contact["UserName"]: contact["NickName"] for contact in contacts}

    def keepRunningAndBlockProcess(self) -> None:
        """
        保持机器人运行，不让进程退出
        """
        while True:
            self.runPendingJobs()
            time.sleep(1)

    def autoAcceptFriendRequest(self, msg: WxMsg) -> None:
        try:
            xml = ET.fromstring(msg.content)
            v3 = xml.attrib["encryptusername"]
            v4 = xml.attrib["ticket"]
            scene = int(xml.attrib["scene"])
            self.wcf.accept_new_friend(v3, v4, scene)

        except Exception as e:
            self.LOG.error(f"同意好友出错：{e}")

    def sayHiToNewFriend(self, msg: WxMsg) -> None:
        nickName = re.findall(r"你已添加了(.*)，现在可以开始聊天了。", msg.content)
        if nickName:
            # 添加了好友，更新好友列表
            self.allContacts[msg.sender] = nickName[0]
            self.sendTextMsg(f"Hi {nickName[0]}，我自动通过了你的好友请求。", msg.sender)

    def newsReport(self) -> None:
        receivers = self.config.NEWS
        if not receivers:
            return

        news = News().get_important_news()
        for r in receivers:
            self.sendTextMsg(news, r)

    def toImageChat(self, msg: WxMsg) -> bool:
        """自定义回复"""
        img_path = "D:\\code\\WeChatRobot\\image\\"

        # 处理图片 OCR 的逻辑
        if msg.extra.endswith(".dat"):
            extra_id = msg.extra.split('/')[-1].split('.dat')[0]
            self.wcf.download_image(msg.id, msg.extra, img_path)
            img_base_64 = img_ocr.image_to_base64(img_path + extra_id + ".jpg")
            secretid = self.config.AKSK.get("secretid")
            secretkey = self.config.AKSK.get("secretkey")
            response = img_ocr.perform_ocr(secretid, secretkey, img_base_64)
            rsp_msg = img_ocr.process_response(response)
            if rsp_msg is not None:
                self.sendTextMsg(rsp_msg, msg.roomid, msg.sender)
            return True

        # 一些固定内容的查询
        image_map = {
            "排位预测": "static\\paiweiyuce.jpg",
            "排位对战": "static\\paiweiyuce.jpg",
            "进阶图": "static\\jinjietu.jpg",
            "玩具扳手": "static\\wanjubanshou.jpg",
            "玩具精铁": "static\\wanjujingtie.jpg",
            "消耗档位": "static\\xiaohaodangwei.jpg",
            "vip对照表": "static\\vipduizhaobiao.jpg",
            "蓝色水晶": "static\\lanseshuijing.jpg",
            "紫色水晶": "static\\ziseshuijing.jpg",
            "橙色水晶": "static\\chengseshuijing.jpg",
            "红色水晶": "static\\hongseshuijing.jpg",
            "金色水晶": "static\\jinseshuijing.jpg",
            "水晶升级表": "static\\shuijingshengjibiao.jpg",
            "水晶升级金砖": "static\\shuijingshengjijinzhuan.jpg",
            "boss血量": "static\\bossxueliang.jpg",
            "boss击杀": "static\\bossjisha.jpg",
            "咸王顺序": "static\\xianwangshunxu.jpg",
            "洗练属性上限": "static\\xilianshuxingshangxian.jpg",
            "洗练计算公式": "static\\xilianjisuangongshi.jpg",
            "俱乐部人数": "static\\juleburenshu.jpg",
            "科技统计": "static\\kejitongji.jpg",
            "武将金币": "static\\wujiangjinbi.jpg",
            "武将进阶石": "static\\wujiangjinjieshi.jpg",
            "武将升星": "static\\wujiangshengxing.jpg",
            "武将满级速度": "static\\wujiangmanjisudu.jpg",
            "主公金币": "static\\zhugongjinbi.jpg",
            "主公进阶石": "static\\zhugongjinjieshi.jpg",
            "灯神奖励": "static\\dengshenjiangli.jpg",
            "灯神礼包": "static\\dengshenlibao.jpg",
            "零氪资源": "static\\lingkeziyuan.jpg",
            "终身通行证资源": "static\\zhongshentongxingzhengziyuan.jpg",
            "氪满资源": "static\\kemanziyuan.jpg",
            "梦境商店": "static\\mengjingshangdian.jpg",
            "十殿1": "static\\shidian1.jpg",
            "十殿一": "static\\shidian1.jpg",
            "十殿2": "static\\shidian2.jpg",
            "十殿二": "static\\shidian2.jpg",
            "十殿3": "static\\shidian3.jpg",
            "十殿三": "static\\shidian3.jpg",
            "十殿4": "static\\shidian4.jpg",
            "十殿四": "static\\shidian4.jpg",
            "十殿5": "static\\shidian5.jpg",
            "十殿五": "static\\shidian5.jpg",
            "十殿6": "static\\shidian6.jpg",
            "十殿六": "static\\shidian6.jpg",
            "十殿7": "static\\shidian7.jpg",
            "十殿七": "static\\shidian7.jpg",
            "十殿8": "static\\shidian8.jpg",
            "十殿八": "static\\shidian8.jpg",
            "鱼珠技能": "static\\yuzhujineng.jpg",
            "鱼珠属性": "static\\yuzhushuxing.jpg",
            "鱼珠技能搭配": "static\\yuzhujinengdapei.jpg",
            "帮助": "static\\bangzhu.jpg",
            "菜单": "static\\bangzhu.jpg"
        }

        # 检查消息内容是否在字典中
        if msg.content in image_map:
            self.wcf.send_image(img_path + image_map[msg.content], msg.roomid)
            return True

        # 处理兑换码的逻辑
        if msg.content == "兑换码":
            self.sendTextMsg(
                "VIP666\n"
                "vip666\n"
                "XY888\n"
                "taptap666\n"
                "QQXY888\n"
                "happy666\n"
                "HAPPY666\n"
                "xyzwgame666\n"
                "huhushengwei888\n"
                "app666\n"
                "APP666\n"
                "douyin666\n"
                "douyin888\n"
                "douyin777",
                msg.roomid,
                msg.sender
            )
            return True

        if msg.content == "到期时间":
            rsp_msg = self.remain_time(self.config.GROUPS_EXPIRE_TIME[msg.roomid])
            self.sendTextMsg(rsp_msg, msg.roomid, msg.sender)
            return True

        if msg.content == "价格":
            rsp_msg = "请给小乖留言详谈"
            self.sendTextMsg(rsp_msg, msg.roomid, msg.sender)
            return True

        return False

    def remain_time(self, expiry_date_str):
        # 设置到期时间
        expiry_date = datetime.strptime(expiry_date_str, '%Y%m%d')

        # 获取当前时间
        current_time = datetime.now()

        # 计算时间差
        time_difference = expiry_date - current_time

        # 提取天数、小时、分钟和秒数
        days = time_difference.days
        seconds = time_difference.seconds
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60

        # 格式化到期时间
        expiry_date_formatted = expiry_date.strftime('%Y年%m月%d日')

        # 返回结果
        return f"到期时间:\n{expiry_date_formatted}，还剩余 【{days}天{hours}小时{minutes}分{seconds}秒】小乖就要离开大大了...[流泪][流泪]"