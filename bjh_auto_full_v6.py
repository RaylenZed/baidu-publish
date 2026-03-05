#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
百家号全流程自动化 v5 — 纯 Python 版 (百度AIGC接口)
====================================================
功能: 随机变量池文章生成 → 润色降AI味 → 百家号自动发布
AI: 百度AIGC接口 (复用百家号cookie, 无需额外API Key)
支持: 5账号 × 18品类 × 41664+种组合

流程 (每个账号):
  1. 从6维变量池随机抽取组合 → 拼装Prompt
  2. 百度AIGC生成初稿 (SSE流式)
  3. 百度AIGC润色降AI味
  4. 百家号API: Token → 草稿 → 封面图 → 发布

使用:
  1. pip install requests
  2. 填写下方 ACCOUNTS 的 cookie
  3. python bjh_auto_full.py

定时运行:
  crontab -e
  0 9 * * * cd /path/to && python3 bjh_auto_full.py >> bjh.log 2>&1
"""

import requests
import json
import re
import time
import random
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

# ============================================================
# ▼▼▼ CONFIG - 只需要改这里 ▼▼▼
# ============================================================

# --- LLM 配置 ---
# 使用百度AIGC接口 (百家号内置AI，复用cookie，无需额外API Key)
# 模型可选: "ds_v3"(DeepSeek), "ernie"(文心一言) 等
BAIDU_AIGC_MODEL = "ds_v3"

# --- 账号配置 ---
ACCOUNTS = [
    {
        "name": "账号1-图书",
        "cookie": """zhishiTopicRequestTime=1772510181314; zhishiTopicRequestTime=1772510272154; zhishiTopicRequestTime=1772515544490; zhishiTopicRequestTime=1772522960354; zhishiTopicRequestTime=1772522991104; XFI=bd5d23e0-1579-11f1-8b00-db2c4e38eb60; Secure; XFCS=6D152CE7CC2F988729941D1EF026C6FFAD643F9D99E82B06D837EE6A16FD6208; Secure; XFT=lWopcX0XfpiRFt9EMvw6cyvc7XRB/GViyp2sjBfpNEU=; Secure; XFI=5ca15690-1653-11f1-9256-b3082dd88be3; XFT=bdaB93qQQzsbyyJ5E1sdFOrftOE0JreWu61TF7OkMGs=; XFCS=CDD87658D9C496D26FB1B8429A269029C5C43E867FF39F207F0ECAB6ADFDD84F; RECENT_LOGIN=0; XFI=2e34c430-1654-11f1-80ba-158c725f8c07; XFCS=5F2B13D7609E116E8D715B64A25EFEFE5DCFB17B631236D52CF9D7686270ED81; XFT=dzGmRVkNmfm4FMqCFEdvBPbbvy1yH2LjaTy3TBDJVLY=; _s_prefix=272e74de0e2b990c0497513ffc146bd3; HttpOnly; Secure; Hm_lvt_04cb53fa27995388defd38a45d165fb5=1772352693; HMACCOUNT=ACD89DC662E433E2; Hm_lpvt_04cb53fa27995388defd38a45d165fb5=1772352717; XFI=a21e1310-1546-11f1-a37e-c7a41f4bfb38; XFCS=EB080AF7B30286D85E89DFAB2399B74F3183B49E3D15FBA34B7BC9C2BF907740; XFT=xNtW/SYY4HtKlGNRwtu5rz1fVd9yNMbD0luQu0A8JNY=; XFI=a4ba68d0-1546-11f1-8cce-dfca4ba674b8; XFCS=91CB64F389EC541E6EAC4AE35FF4FE3D909D744F6A7E7A35574336D1B815A1B4; XFT=YRGTQY9+fXp1NoUPaZ/6Wi0wIRY1iMtgAs7TbrtkP5M=; HMACCOUNT_BFESS=ACD89DC662E433E2; Secure; BD_UPN=123253; ab_jid=56e9507f7eb706a1fe9eae76ca740f174783; HttpOnly; Secure; ab_jid_BFESS=56e9507f7eb706a1fe9eae76ca740f174783; HttpOnly; Secure; HOSUPPORT=1; HttpOnly; HOSUPPORT_BFESS=1; HttpOnly; Secure; USERNAMETYPE=1; HttpOnly; USERNAMETYPE_BFESS=1; HttpOnly; Secure; sug=3; sugstore=1; ORIGIN=0; bdime=0; DOUJIN_CUID=4b534c47-7c37-4268-7b36-177142258811; Secure; BAIDUCUID=4b534c47-7c37-4268-7b36-177142258811; Secure; IV=D1A5179920ED6A2BED7FEF09E6B8DA95; HttpOnly; Secure; log_guid=33fbb98950761a8d796768db81c2545a; Secure; XFS=vFk3Np4%2F5Utu6OR3isASZYfmjTElRzi%2FQMJ2TH1sgWo%3D; bce-login-type=PASSPORT; Secure; bce-login-type-detail=NORMAL_PASSPORT; Secure; bce-passport-stoken=929394f7967f46576efe12faee01295c88c8adae5e82c72939bc34323065d211; Secure; bce_mfa_type=PHONE%2CTOTP; Secure; bce-login-accountid=128839b764e446f4b69cfbe28929b874; bce_mfa_cause=LOGIN; Secure; bce-login-display-name=zhangleileix; bce-login-domain-account=zhangleileix; Secure; bce-auth-type=PASSPORT; Secure; bce-sessionid=001a1c82b5bfa034386876b83350c8c4708; HttpOnly; Secure; bce-long-term-sessionid=001f29f96f3fdf44d6ab3989ed6320ee3b8; HttpOnly; Secure; bce-ctl-client-cookies="BDUSS,BDUSS_BFESS,bce-passport-stoken,bce-device-cuid,bce-device-token,BAIDUID"; Secure; bce-ctl-client-parameters=brt; Secure; bce-ctl-client-headers=""; Secure; bce-user-info="2026-03-01T15:41:05Z|712ca4fec9764710a697b6369eaee484"; Secure; bce-userbind-source=PASSPORT; Secure; bce-session=128839b764e446f4b69cfbe28929b8748e33101c3cce4f8882c838d5729ce86e|40780d64c96338dfc9ecaca3bb261df0; HttpOnly; Secure; bce-ctl-sessionmfa-cookie=bce-session; Secure; bceAccountName=PASSPORT:4044184706; bce-ctl-client-cookies="BDUSS,BDUSS_BFESS,bce-passport-stoken,bce-device-cuid,bce-device-token,BAIDUID"; bce-passport-stoken=929394f7967f46576efe12faee01295c88c8adae5e82c72939bc34323065d211; bce-ctl-sessionmfa-cookie=bce-session; bce-session=128839b764e446f4b69cfbe28929b8748e33101c3cce4f8882c838d5729ce86e|40780d64c96338dfc9ecaca3bb261df0; bce-login-display-name=zhangleileix; bce-userbind-source=PASSPORT; bce-auth-type=PASSPORT; bce-login-type=PASSPORT; bce-login-expire-time="2026-03-01T08:11:06Z|e0eed9759034c6933d67062719725ec6"; loginUserId=4044184706; CAMPAIGN_TRACK=developer-home-banner; Hm_lvt_28a17f66627d87f1d046eae152a1c93d=1772350923; Hm_lpvt_28a17f66627d87f1d046eae152a1c93d=1772350923; HMACCOUNT=ACD89DC662E433E2; CAMPAIGN_TRACK_TIME=2026-03-01+15%3A42%3A03; bce-login-accountid=128839b764e446f4b69cfbe28929b874; bceAccountName=PASSPORT:4044184706; bce-ctl-client-cookies="BDUSS,BDUSS_BFESS,bce-passport-stoken,bce-device-cuid,bce-device-token,BAIDUID"; bce-passport-stoken=929394f7967f46576efe12faee01295c88c8adae5e82c72939bc34323065d211; bce-user-info="2026-03-01T15:41:05Z|712ca4fec9764710a697b6369eaee484"; bce-user-info-ct-id="712ca4fec9764710a697b6369eaee484"; bce-ctl-sessionmfa-cookie=bce-session; bce-session=128839b764e446f4b69cfbe28929b8748e33101c3cce4f8882c838d5729ce86e|40780d64c96338dfc9ecaca3bb261df0; bce-login-display-name=zhangleileix; bce-userbind-source=PASSPORT; bce-auth-type=PASSPORT; bce-login-type=PASSPORT; bce-login-expire-time="2026-03-01T08:11:06Z|e0eed9759034c6933d67062719725ec6"; loginUserId=4044184706; bce-user-info="2026-03-01T15:41:05Z|712ca4fec9764710a697b6369eaee484"; BD_CK_SAM=1; __cas__st__558=NLI; HttpOnly; __cas__id__558=0; HttpOnly; __cas__rn__558=0; HttpOnly; LOGIN_OPT_=0; HttpOnly; Hm_lvt_0db18a3ce977f2c77edf8e7a00bf159d=1772351061,1772352733; Hm_lpvt_0db18a3ce977f2c77edf8e7a00bf159d=1772352733; PHPSESSID=niucbd2arfsvri946pp3hn1mp0; Hm_lvt_912efd4e2e75ff91305c5ebd0114ff98=1772352854; HMACCOUNT=ACD89DC662E433E2; Hm_lpvt_912efd4e2e75ff91305c5ebd0114ff98=1772352858; SITEMAPZHITONG={"data":"3bc95f8a6e0c0c6b2fa267cce31564ee9bc06e5310be1cc3b2fe3f0f81e022c4a54d3353daac4ef62762a90fd1ae0ad29c16484d7b952399c2701a7df895a82751f6fbb5e8eeeb99264f1ff00a9647c282369c8ab9d02df39d5fef740079b594def402a00248eb5a2a0db2222bdcb16889af89be83495333bd7f482f546685238597f72a52d8e9f8fad4d1a7694b5207a16ff97f1cc9379c2d31ad6ce7ebe002ad90c5b91167a8c6494096749141c1e2e4c4fda0cc2b26b4533bbfaa1f2c05801131c4314b280641b2df44041394a3968d21b4098732220a204734c7bb99caf29c0ef852f1a1e934bb1307f899d45cf2d3217fa3a5a1cb43e59e6e5ab0e0a39ab6be7d5d50bef64484a78ef0f829b2e52b23cdb6516bbc0760fba84d6265499228a814295dc8fd191ff9ce8e3c055f4c7f4d8a1ed78ca8d51fdccf5c2f61696670e7073e2880bab557d22e91149ccb8920b405a31891f53542d142e9229c0b973f4d0f9095d110d00fbfaad77f17aa5c64e724d62c8ce813a14bab0f05a23979","key_id":"32","sign":"e99f8469"}; XFI=aa4a5c10-1546-11f1-9d3f-59e92ce4fb22; XFCS=BCD46BB45B535ED11FE7943A2A98D0D1064E586A693D716D88F8E69C3E095641; XFT=tMF+efFsK2OprPHYZ1PzsdT5xPhrMusBM8NJdqXouIM=; Hm_lvt_6859ce5aaf00fb00387e6434e4fcc925=1772352885; Hm_lpvt_6859ce5aaf00fb00387e6434e4fcc925=1772352885; HMACCOUNT=ACD89DC662E433E2; BIDUPSID=1F272897E1624C651D85D0A211256FCD; Secure; PSTM=1763531964; Secure; BAIDUID=D8D63964C1517AFAECF7829EADDCCD64:SL=0:NR=10:FG=1; Secure; MCITY=-131%3A; Secure; theme=bjh; Secure; Hm_lvt_192fa266ff34772c28e4ddb36b8f4472=1770308757; Secure; newlogin=1; HttpOnly; Secure; Hm_lvt_f7b8c775c6c8b6a716a75df506fb72df=1770307820,1770367478,1771328208,1772299078; Secure; HMACCOUNT=ACD89DC662E433E2; Secure; PHPSESSID=dv19hhf2rvsvf6em3vg1os6of7; Secure; Hm_lvt_f2ee7f5c2284ca4c112e62165bc44c75=1772350646; Secure; Hm_lpvt_f2ee7f5c2284ca4c112e62165bc44c75=1772350646; Secure; bce-sessionid=001a1c82b5bfa034386876b83350c8c4708; HttpOnly; Secure; H_PS_PSSID=67081_67496_67602_67644_67754_67745_67312_67835_67854_67857_67850_67860_67862_67863_67870_67884_67888_67894_67941_67959_67951_67954_67955_67962_67883_67991_68026_68045_68076_68094_68088; Secure; BAIDUID_BFESS=D8D63964C1517AFAECF7829EADDCCD64:SL=0:NR=10:FG=1; Secure; delPer=0; Secure; PSINO=2; Secure; ZFY=Ocq9AelcelC:BhzeCTNnhOuaHjd89:A8c7kfYhp0ZEyVw:C; Secure; __bid_n=19ca541d5f74384fe02b8b; Secure; ZD_ENTRY=baidu; Secure; BDRCVFR[feWj1Vr5u3D]=I67x6TjHwwYf0; Secure; H_WISE_SIDS=110085_660925_667681_675908_679558_681989_681439_685387_686275_686539_687605_687680_687788_687726_688710_688784_689225_686419_689171_689318_689379_688173_687425_682131_689429_689656_689118_689674_687640_689767_688610_688100_689901_689912_689890_689919_689872_689913_689884_689906_690073_690100_688483_690117_690125_690221_689120_690234_690225_687518_690239_689941_687081_690298_686804_690342_690340_690478_690383_690501_690363_687859_8000064_8000124_8000135_8000150_8000161_8000175_8000178_8000190_8000202_8000203; Secure; H_WISE_SIDS_BFESS=110085_660925_667681_675908_679558_681989_681439_685387_686275_686539_687605_687680_687788_687726_688710_688784_689225_686419_689171_689318_689379_688173_687425_682131_689429_689656_689118_689674_687640_689767_688610_688100_689901_689912_689890_689919_689872_689913_689884_689906_690073_690100_688483_690117_690125_690221_689120_690234_690225_687518_690239_689941_687081_690298_686804_690342_690340_690478_690383_690501_690363_687859_8000064_8000124_8000135_8000150_8000161_8000175_8000178_8000190_8000202_8000203; Secure; ppfuid=FOCoIC3q5fKa8fgJnwzbE0LGziLN3VHbX8wfShDP6RCsfXQp/69CStRUAcn/QmhIlFDxPrAc/s5tJmCocrihdwitHd04Lvs3Nfz26Zt2holplnIKVacidp8Sue4dMTyfg65BJnOFhn1HthtSiwtygiD7piS4vjG/W9dLb1VAdqNxQIwqM3OslymmN1WQYZqbO0V6uxgO+hV7+7wZFfXG0MSpuMmh7GsZ4C7fF/kTgmt3jpj+McMorhe+Cj/9lStSBwMLYHXX6sSySAfDc47AfQqYgheSYkz7BDnJkD5v5D41v2iwj13daM+9aWJ5GJCQu/SUbF5jV5AUyz/jBiIgKVObaDCHgWJZH3ZrTGYHmi7XJB9z3y2o8Kqxep5XBCsuFKJEamDWP0B99HzIVbHvreUvX0kas1bUazspdZgjdxkW3V0FZ0N5PBhXV/YkJXkLFeLs4wygIv6m069lhsdmzXKHw09ZoLr0lxODZXVxpk7QFXV1C8qyUqcAnBm7hcJuxcqfdReixTVTfT+miI3ZV5eQE96jz5eP/gEigLYjtZnrOQVr9TB3lK8L3WS99/Zr9ng7DJNA0zsRL0eZGEKF1aDRInbESzVqJcCK3XpGJOV/zZ6wkf5f+PnYbtHcSvBB4lPdCgO/rhHbvTb7w1sYiN/Vk5/GFQKmYmpXiN4dJoe04sIEztQcQ/Sj8aeZwWg0mAteMeU9qyn6SoJvv6345Qt76XFBJWSgbZ6/F0ZRwCDo0NPL3fh6V0Qf84X0lHCG5fhO+iiq5YumIdRwlIsr30EHBU5EkTU9kd+430DO0D0/RfSjBZQtncCqzoyNORJDcav1VQU9Nb3SpOs6OnNPHvOBRFTC3dJt11rYxTmLu8GIDQxqMKltDwwpum3Juw8bhBgKsG2JlL29AEHRUoKNa0CrXiJwBTbsQ97ckDDWTffZfhpcog1PhEwkcbrqGW8fZYT/7PFz8Y1PZo7KIEM+Ag7vVtkGN3nMKm3rd2mDkhNuquWLv5kuJDMwwerkeHUP9Bq7zt2A9A8E851l8QtBoQFIuWEGY3DMQGzE4fLtBnD2IBA1xgIrbF95h/aKYBNVXdvBhoLwXhcnXaiqXEpcvFQlonIv85FfaVbfEoKujQX2IBA1xgIrbF95h/aKYBNVh6Y0NjEKZ13xldTgKDiG2QRBJFTPsviSSEvgLGRO3YgGOv+/I3nwGp9q5hLF8/07goRUnieOy9WY3CCu1FKQrdt1aNEEKzFfteUuHCilwCtbHhSGlEKo+S0ciyUHoRYU; Secure; BDUSS=040WUJ5bGw2QUlJTFpHTTV3bzJjSG9SZi0zdFBiOUxJR3dwa0tKVGxicnIxTXRwRVFBQUFBJCQAAAAAAAAAAAEAAACCXA3xemhhbmdsZWlsZWl4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOtHpGnrR6RpR; HttpOnly; Secure; BDUSS_BFESS=040WUJ5bGw2QUlJTFpHTTV3bzJjSG9SZi0zdFBiOUxJR3dwa0tKVGxicnIxTXRwRVFBQUFBJCQAAAAAAAAAAAEAAACCXA3xemhhbmdsZWlsZWl4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOtHpGnrR6RpR; HttpOnly; Secure; Hm_lpvt_f7b8c775c6c8b6a716a75df506fb72df=1772374786; Secure; RECENT_LOGIN=0; Secure; devStoken=86f3501a35ecf438b3be66d054b8c26699c27e9c66c2fb6fc150b63d2f949687; HttpOnly; Secure; bjhStoken=21de0b0f557782e195083bff084c61cc99c27e9c66c2fb6fc150b63d2f949687; HttpOnly; Secure; XFI=b463c6e0-1579-11f1-95c3-71613c13f849; Secure; XFCS=60083F30B9E7C9D9258D6EB9C6D4B03E278CC1DE048E9EF488688F29267A81B8; Secure; XFT=w/qInVGR/D+KgCdz7/1VF2ZtO/eONcMjJE6eccWUQl0=; Secure; RT="z=1&dm=baidu.com&si=ba34524c-a23b-4b79-97f8-46739b55e790&ss=mm7tp3zq&sl=3&tt=9do&bcn=https%3A%2F%2Ffclog.baidu.com%2Flog%2Fweirwood%3Ftype%3Dperf&ld=hp5s"; Secure; BAIDUID=C25B5AEBFD011E9B02C18B40F423DC7F:FG=1; Secure; BAIDUID_BFESS=C25B5AEBFD011E9B02C18B40F423DC7F:FG=1; Secure; PHPSESSID=l0jm3rl4dgeg6mi7d1tsb3ft71; Secure; theme=bjh; Secure; devStoken=86f3501a35ecf438b3be66d054b8c26624e595ec9efeaef6a843dd5dc7f4e03f; HttpOnly; Secure; bjhStoken=21de0b0f557782e195083bff084c61cc24e595ec9efeaef6a843dd5dc7f4e03f; HttpOnly; Secure; ppfuid=FOCoIC3q5fKa8fgJnwzbE0LGziLN3VHbX8wfShDP6RCsfXQp/69CStRUAcn/QmhIlFDxPrAc/s5tJmCocrihdwitHd04Lvs3Nfz26Zt2holplnIKVacidp8Sue4dMTyfg65BJnOFhn1HthtSiwtygiD7piS4vjG/W9dLb1VAdqNxQIwqM3OslymmN1WQYZqbO0V6uxgO+hV7+7wZFfXG0MSpuMmh7GsZ4C7fF/kTgmt3jpj+McMorhe+Cj/9lStSBwMLYHXX6sSySAfDc47AfQqYgheSYkz7BDnJkD5v5D41v2iwj13daM+9aWJ5GJCQu/SUbF5jV5AUyz/jBiIgKVObaDCHgWJZH3ZrTGYHmi7XJB9z3y2o8Kqxep5XBCsuFKJEamDWP0B99HzIVbHvreUvX0kas1bUazspdZgjdxkW3V0FZ0N5PBhXV/YkJXkLFeLs4wygIv6m069lhsdmzXKHw09ZoLr0lxODZXVxpk7QFXV1C8qyUqcAnBm7hcJuxcqfdReixTVTfT+miI3ZV5eQE96jz5eP/gEigLYjtZnrOQVr9TB3lK8L3WS99/Zr9ng7DJNA0zsRL0eZGEKF1aDRInbESzVqJcCK3XpGJOV/zZ6wkf5f+PnYbtHcSvBB4lPdCgO/rhHbvTb7w1sYiN/Vk5/GFQKmYmpXiN4dJoe04sIEztQcQ/Sj8aeZwWg0mAteMeU9qyn6SoJvv6345Qt76XFBJWSgbZ6/F0ZRwCDo0NPL3fh6V0Qf84X0lHCG5fhO+iiq5YumIdRwlIsr30EHBU5EkTU9kd+430DO0D0/RfSjBZQtncCqzoyNORJDcav1VQU9Nb3SpOs6OnNPHvOBRFTC3dJt11rYxTmLu8GIDQxqMKltDwwpum3Juw8bhBgKsG2JlL29AEHRUoKNa0CrXiJwBTbsQ97ckDDWTffZfhpcog1PhEwkcbrqGW8fZYT/7PFz8Y1PZo7KIEM+Ag7vVtkGN3nMKm3rd2mDkhNuquWLv5kuJDMwwerkeHUP9Bq7zt2A9A8E851l8QtBoQFIuWEGY3DMQGzE4fLtBnD2IBA1xgIrbF95h/aKYBNVXdvBhoLwXhcnXaiqXEpcvFQlonIv85FfaVbfEoKujQX2IBA1xgIrbF95h/aKYBNVh6Y0NjEKZ13xldTgKDiG2QRBJFTPsviSSEvgLGRO3YgGOv+/I3nwGp9q5hLF8/07goRUnieOy9WY3CCu1FKQrdt1aNEEKzFfteUuHCilwCtbHhSGlEKo+S0ciyUHoRYU; Secure; RT="z=1&dm=baidu.com&si=ba34524c-a23b-4b79-97f8-46739b55e790&ss=mm7tp3zq&sl=4&tt=h7a&bcn=https%3A%2F%2Ffclog.baidu.com%2Flog%2Fweirwood%3Ftype%3Dperf&ld=i1jm"; Secure; theme=bjh; PHPSESSID=qlrkch1dfvmdlvgfatggt91n24; ppfuid=FOCoIC3q5fKa8fgJnwzbE0LGziLN3VHbX8wfShDP6RCsfXQp/69CStRUAcn/QmhIlFDxPrAc/s5tJmCocrihdwitHd04Lvs3Nfz26Zt2holplnIKVacidp8Sue4dMTyfg65BJnOFhn1HthtSiwtygiD7piS4vjG/W9dLb1VAdqNxQIwqM3OslymmN1WQYZqbO0V6uxgO+hV7+7wZFfXG0MSpuMmh7GsZ4C7fF/kTgmt3jpj+McMorhe+Cj/9lStSBwMLYHXX6sSySAfDc47AfQqYgheSYkz7BDnJkD5v5D41v2iwj13daM+9aWJ5GJCQu/SUbF5jV5AUyz/jBiIgKVObaDCHgWJZH3ZrTGYHmi7XJB9z3y2o8Kqxep5XBCsuFKJEamDWP0B99HzIVbHvreUvX0kas1bUazspdZgjdxkW3V0FZ0N5PBhXV/YkJXkLFeLs4wygIv6m069lhsdmzXKHw09ZoLr0lxODZXVxpk7QFXV1C8qyUqcAnBm7hcJuxcqfdReixTVTfT+miI3ZV5eQE96jz5eP/gEigLYjtZnrOQVr9TB3lK8L3WS99/Zr9ng7DJNA0zsRL0eZGEKF1aDRInbESzVqJcCK3XpGJOV/zZ6wkf5f+PnYbtHcSvBB4lPdCgO/rhHbvTb7w1sYiN/Vk5/GFQKmYmpXiN4dJoe04sIEztQcQ/Sj8aeZwWg0mAteMeU9qyn6SoJvv6345Qt76XFBJWSgbZ6/F0ZRwCDo0NPL3fh6V0Qf84X0lHCG5fhO+iiq5YumIdRwlIsr30EHBU5EkTU9kd+430DO0D0/RfSjBZQtncCqzoyNORJDcav1VQU9Nb3SpOs6OnNPHvOBRFTC3dJt11rYxTmLu8GIDQxqMKltDwwpum3Juw8bhBgKsG2JlL29AEHRUoKNa0CrXiJwBTbsQ97ckDDWTffZfhpcog1PhEwkcbrqGW8fZYT/7PFz8Y1PZo7KIEM+Ag7vVtkGN3nMKm3rd2mDkhNuquWLv5kuJDMwwerkeHUP9Bq7zt2A9A8E851l8QtBoQFIuWEGY3DMQGzE4fLtBnD2IBA1xgIrbF95h/aKYBNVXdvBhoLwXhcnXaiqXEpcvFQlonIv85FfaVbfEoKujQX2IBA1xgIrbF95h/aKYBNVh6Y0NjEKZ13xldTgKDiG2QRBJFTPsviSSEvgLGRO3YgGOv+/I3nwGp9q5hLF8/07goRUnieOy9WY3CCu1FKQrdt1aNEEKzFfteUuHCilwCtbHhSGlEKo+S0ciyUHoRYU; Secure; PSTM=1772386874; BAIDUID=C55BF7D408BC93E64C464B6FAE0BF9E5:FG=1; H_PS_PSSID=63147_67495_67601_67644_67722_67748_67752_67313_67725_67834_67857_67853_67852_67860_67864_67862_67868_67869_67884_67890_67908_67942_67914_67951_67953_67956_67966_67877_67883_68052_68076_68081_68100_68102; BD_HOME=1; BIDUPSID=1F272897E1624C651D85D0A211256FCD; BAIDUID_BFESS=C55BF7D408BC93E64C464B6FAE0BF9E5:FG=1; Secure; ZFY=Ocq9AelcelC:BhzeCTNnhOuaHjd89:A8c7kfYhp0ZEyVw:C; Secure; PSINO=2; delPer=0; H_WISE_SIDS=63147_67495_67601_67644_67722_67748_67752_67313_67725_67834_67857_67853_67852_67860_67864_67862_67868_67869_67884_67890_67908_67942_67914_67951_67953_67956_67966_67877_67883_68052_68076_68081_68100_68102; UBI=fi_PncwhpxZ%7ETaL91LNqe-WBV3S1Pxg53KmDN0emdlj1brQPYEMfZQ-UohQCbP60EAOUMid5OK5A61L-GQB; HttpOnly; UBI_BFESS=fi_PncwhpxZ%7ETaL91LNqe-WBV3S1Pxg53KmDN0emdlj1brQPYEMfZQ-UohQCbP60EAOUMid5OK5A61L-GQB; HttpOnly; Secure; logTraceID=de3f6143019f0e9d7ef9005c8c5672050a0032158dc00e8817; pplogid=5367lF%2BJYLJmSnfVRDhFqnQH0uARCnS64ajfGtusLbkH5B2l2vPhEK3rXmb4yMMIJcuxTOyDroYhwKCB4YD2UnKjrlfnPa%2FX6M%2FZMjSoXBZf5LfYrc7uAhM48fToy0e%2FmJ2y; HttpOnly; pplogid_BFESS=5367lF%2BJYLJmSnfVRDhFqnQH0uARCnS64ajfGtusLbkH5B2l2vPhEK3rXmb4yMMIJcuxTOyDroYhwKCB4YD2UnKjrlfnPa%2FX6M%2FZMjSoXBZf5LfYrc7uAhM48fToy0e%2FmJ2y; HttpOnly; Secure; STOKEN=949c8dbfd59baa8c9f9aec073bc7f47490e247d72b5433c2ad6bd37e51742834; HttpOnly; Secure; BDUSS=XY0MjBVUVBDdTJqS3FVSnVjSGw0amlzUGdQcVVRa1F5c0dTdjNTMmFNZENSYzFwRVFBQUFBJCQAAAAAAQAAAAEAAABQmJWiAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEK4pWlCuKVpV; HttpOnly; PTOKEN=5d8f24479a005502d9b0ae0d1a1573f2; HttpOnly; Secure; BDUSS_BFESS=XY0MjBVUVBDdTJqS3FVSnVjSGw0amlzUGdQcVVRa1F5c0dTdjNTMmFNZENSYzFwRVFBQUFBJCQAAAAAAQAAAAEAAABQmJWiAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEK4pWlCuKVpV; HttpOnly; Secure; STOKEN_BFESS=949c8dbfd59baa8c9f9aec073bc7f47490e247d72b5433c2ad6bd37e51742834; HttpOnly; Secure; PTOKEN_BFESS=5d8f24479a005502d9b0ae0d1a1573f2; HttpOnly; Secure; Hm_lvt_f7b8c775c6c8b6a716a75df506fb72df=1772374819,1772468292; HMACCOUNT=ACD89DC662E433E2; __bid_n=19ca541d5f74384fe02b8b; Hm_lvt_400790f61cbe0e7d1d9cae19d202e8ce=1770367846,1771769939,1772299598,1772468299; Hm_lpvt_400790f61cbe0e7d1d9cae19d202e8ce=1772468299; HMACCOUNT=ACD89DC662E433E2; XFI=6d2146b0-1653-11f1-84b0-6b416d810ecd; XFCS=F6958CF46E8F78A55A6E9745B03FDCE2050FBD6642FE4C71815059EC7B28DC70; saas-appinfo=eyJhbGciOiJkaXIiLCJlbmMiOiJBMjU2R0NNIn0..7NgZBXHygrdDpZ5S.WffEos-ziGjd7vKKVNriPqmSZ3rmiJc4T1Mn4uMrweiI9wsGNR7uIrx-JQ6G6nN2Ym88aPuJ_hMKmAbfFxMObnVIOWuEXHZcdxNPMa_irRBXikxTm_88XlwB783S2uQW6BgCOuAVioiF_rgmXrzkm0i0cWnv7mpcb_nIJyciqSmFWm6KQ0szSaRIvih4BQWJU1WbH2Gmis1AEnxnwazFTlgjVgeOk05cAhIYOGdN9mHdsZtalyR-sz31vwefAr49ozbHiEHmua4c_Wf0h64h3Ps10qwbMDnloQezDfjT0xFrpnLL90igYSzyY6LvVsU_4vCMnuNTFVqYudldciW8RBWquyRd91qDrlqYO-pHxL12IsLFq8UoJZ8QevONWJdf7mdo0CGj3-yj1EW7W8_hAT0DNZwQsSkPGwMyTdBO2dZ9dgHaj9gnbVl18ErMT4KTuEEBW3YELIqwy3Lp5QMRn58FXRK3vKCmSF6ZHzYQU5-hCizq5FKQLIV1C5MatVoITg9Zfh6oxw-RySOD41Ui96_163xUR0vM4eLwEKRYlZCk5Ozqh7HyHaYTc0mmq7lBG3Rz5k4ULDWeeucBXJWYSLgkhJTtHQAzH3ancm1AtrWuSZ2tHzXRXaycHmH8ckFK_Z-hnTAVaYxKSX5K2KwD9ZzwD2c7tIig-7JSL9HXmB0v9ynm2VP2j0imnSq2lbcIteApiUPq4jEy92GfEykN1cc72m8WFuMsAdUVSnt0BBIG3eF2FF0xt6CzGS7rg9vAzmPpPAKVxAHvOW4_aTUBz36-UbdFavA70fSDBvmwAPiSK0pOKwdiF3aLs1YxJ08aWzZVo75o3DC4_UehqcNq1OfHSpaWhXDLbx5TchQuK4P0s0G4DN6Oa72Mr2-BHIuBobCVtVVhMesxV-B1I4PrCxg0gUxmXQDYIElJp977uNJnbhGhBfIG0vkSgAswDvYanYs6OOTi0eB38NHe__5Jmmp5VVSaNeKMsy5sHxpdRsnSEVopFxorwyYUj9sD0JcoUgEMNKXPe66PtKT5b5VUeNJUzPs7BB9jV_cA6J1ZmsKXpDrFqXSX4Uy4gGIL7Yd-VZWn97KoDCypZXQt3c-9TrWCNysqM9mdM84zAtGZVFxewIwkdpyS6pGoMEgSSKS41OrWO4uZ0C_l3bQV-Q0wvzyWXe2QelrJOPGWKSAnhDJvN1FbTPX3n3I5pSDXiqU-bJxByt8y4QaR6Q0841SgPc_w_DuTeAn4FaD3FgvHAJwsxW2q8Av-zAidToKVsXtSe4I9ZkLjQyUK31TGhP5pnCzt2DW1HzOgqZ_XhvY_9isopJi1TDk4zJ8mhje9TYbcWYcWpChd7x4t1lFdi9RwlSXDR_BuJ8GFtGuhYZvUW6PERcR6Bm3FC0HgfR3-tVBnZ0pejeYYk_bhMpRlBRKVxiK_Gnzm3UTyqpUxbU7k1WNgJBpRQWdNr7VT4UeGfw2ovDkcQo6n40twl21RR6rCuqNoVUTDD69VIhZf2RVPot01P1uuozkdW-Q7Btyoz0SCwiB2JRpoXrrfLSAVK4czSaNGYTB-rAI-WmWmhfhYfGckMJOYkwuaWfrbNyTn29hrfxjoy4Z3p_i6BmGyzaf86RL4Kqo-S6gOWyHQi6a2h4z_W3kW0qs5qhqAtvoHcGPC096iOPJx7FXwAzTlClY-J3DZg_rRUwsyHBWYqJfshqNhRtsYzsGp-W_M_D6RYnn9W-0_ZgnSqgWHGrIBMUajhS9nuK_hVgphmRMCOwUAByN6CxqIidX1M-uuxmO9I8OSbo3XoWp1yR7jG9yGIM7Sx20oDfaB_yxYfK56rGJ9WJkJabCZ6ZHCQESP8t3DFtiEJJMdfvtQNLaw8Ck2hSsfW4y2-8lm4mBnq-mdcUN6900cULvmtvH6TpoQgkiuMZq79hlc59U0kTdnu418bb2OPMbNvgh_5ZIlad-yNqD9tfPoHUwgiJ9xVdUdsR1E90ZYoYmy-vQbVg4ZGZ6oT61QCneXEpX3wsXfc9X3gZKo8EK75QlHEK3XtF0T_wTckPlBvbO2Rx64JQ7cThfIOQwhA8ksK1tLpR10f-DCpqjDZQJ0L4sxtKtNLvXuC5I6uEQ_By8ZjbKzr6SAri7K353O_cRCueFEmxd5EjWgnz-OEsc3eRwk6Y2Ha9tdsqlKBHJrdxROk6ae8OiCZZDx6BctCaokPRvjImhes3HE8vPKsg.3yuw_MMP2BQATOg1ZCmWRg; channel=google; baikeVisitId=497db0de-91fb-4e51-ac99-4b448f71dd25; Hm_lpvt_f7b8c775c6c8b6a716a75df506fb72df=1772553034; RT="z=1&dm=baidu.com&si=ba34524c-a23b-4b79-97f8-46739b55e790&ss=mmasb6h5&sl=0&tt=0&bcn=https%3A%2F%2Ffclog.baidu.com%2Flog%2Fweirwood%3Ftype%3Dperf"; RECENT_LOGIN=0; ab_bid=1f5bb244abdada1261fd59fa09d225cf6a72; HttpOnly; Secure; ab_sr=1.0.1_NzQ5MWFiYjFlOGVlNzhiZTk5YzFmZGQ5NjBhMDA4ZTRhOWMwZTJkYjE1MTk2ODI1YzM2MGE0MDU1ZjgyZTlmOGU1MTNmMzU0MGRmYmEyMjg1MWE0ZDcxNzcwZDU5NjQyZTFiOTllOGY0YzIzODhjY2I4MjJhODNkNDg5YWUwNmU0NGIwYjY1ZWQwMDNjNGIwZTYyNjg3OTJhMjQwNWEyZWQ3NzBjODFiMzI1ZWUzYmZhNDRjNjE0Y2IxNDRhNzgy; HttpOnly; Secure; XFI=b803b260-1718-11f1-a522-3da26b06b634; devStoken=4a9cd37cd9899e5dc9a4642898c78df419f83fb18ae30078a3b883589938d6f5; HttpOnly; bjhStoken=c5f906663a11ee295262a22202a43e0919f83fb18ae30078a3b883589938d6f5; HttpOnly; XFCS=6E63813EB56FF2C0B4DD53808F929DC68068D93DCCEBBFE54F5AFECDF2B3145F""",
        "categories": ["图书教育"]
    },
    # {
    #     "name": "账号2-家居服饰",
    #     "cookie": "在这里填入账号2的完整cookie",
    #     "categories": ["家用日常", "精品服饰"]
    # },
    # {
    #     "name": "账号3-数码",
    #     "cookie": "在这里填入账号3的完整cookie",
    #     "categories": ["数码家电"]
    # },
    # {
    #     "name": "账号4-美妆母婴",
    #     "cookie": "在这里填入账号4的完整cookie",
    #     "categories": ["美妆个护", "母婴用品"]
    # },
    # {
    #     "name": "账号5-食品",
    #     "cookie": "在这里填入账号5的完整cookie",
    #     "categories": ["食品生鲜"]
    # },
]

# --- 运行模式 ---
# "publish" = 正式发布, "draft" = 只保存草稿不发布
RUN_MODE = "publish"

# --- 账号间延迟(秒)，避免过快触发风控 ---
ACCOUNT_DELAY = 10

# ============================================================
# ▲▲▲ CONFIG 结束 ▲▲▲
# ============================================================


# ============================================================
# 日志配置
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger("BJH")


# ============================================================
# 变量池系统 — 18品类 × 6维度
# ============================================================

# --- 18个品类专属角度池 ---
ANGLE_POOL = {
    "图书教育": ["书单推荐", "读后感", "阅读方法论", "冷门好书发现", "经典重读", "场景化推荐", "书中金句分享", "一本书改变了我什么", "同主题对比阅读", "避坑指南", "亲子阅读", "书与影视对比", "职场成长书单"],
    "家用日常": ["好物测评", "收纳整理", "清洁技巧", "家居好物分享", "省钱攻略", "囤货清单", "旧物改造", "租房好物", "搬家必备", "家务效率", "厨房神器", "浴室好物"],
    "精品服饰": ["穿搭分享", "衣橱整理", "风格探索", "季节穿搭", "微胖穿搭", "小个子穿搭", "通勤穿搭", "约会穿搭", "面料科普", "品牌故事", "二手中古", "配色技巧"],
    "食品生鲜": ["美食测评", "食材挑选", "厨房小白教程", "地方特色美食", "减脂餐分享", "早餐灵感", "懒人快手菜", "零食测评", "养生食谱", "应季水果推荐", "调味料推荐", "一人食"],
    "数码家电": ["开箱测评", "使用技巧", "选购指南", "性价比推荐", "避坑经验", "新品体验", "老产品翻新", "配件推荐", "智能家居搭建", "拍照技巧", "效率工具", "数码极简"],
    "美妆个护": ["护肤心得", "化妆教程", "成分分析", "空瓶记", "平价替代", "敏感肌护理", "防晒攻略", "香水分享", "美甲灵感", "身体护理", "医美科普", "素颜养肤"],
    "母婴用品": ["育儿经验", "好物种草", "辅食制作", "月子日记", "婴儿用品测评", "亲子游戏", "宝宝睡眠", "二胎生活", "孕期好物", "儿童安全", "早教分享", "断奶经历"],
    "运动户外": ["跑步记录", "健身入门", "装备测评", "徒步攻略", "骑行日记", "瑜伽分享", "游泳技巧", "露营体验", "登山故事", "减肥打卡", "运动损伤预防", "居家锻炼"],
    "鞋靴箱包": ["鞋子测评", "包包推荐", "搭配灵感", "通勤包选择", "旅行箱推荐", "球鞋文化", "皮具保养", "小众品牌", "学生党推荐", "经典款盘点", "二手鉴定", "收纳技巧"],
    "汽车用品": ["车品推荐", "自驾游好物", "新手司机必备", "车内收纳", "洗车养护", "行车记录仪", "车载数码", "改装分享", "停车技巧", "省油经验", "安全配件", "长途必备"],
    "珠宝配饰": ["首饰搭配", "珠宝科普", "小众设计", "日常佩戴", "婚戒选择", "保养技巧", "材质对比", "送礼推荐", "古风饰品", "时尚趋势", "DIY手工", "宝石鉴赏"],
    "宠物用品": ["养宠日常", "宠物用品测评", "喂养指南", "宠物健康", "新手养猫", "新手养狗", "宠物玩具", "宠物美容", "领养故事", "多宠家庭", "异宠分享", "宠物训练"],
    "鲜花园艺": ["养花心得", "绿植推荐", "阳台花园", "花艺搭配", "多肉养护", "水培技巧", "四季花历", "花市淘货", "办公桌绿植", "庭院设计", "干花制作", "送花指南"],
    "零食干货": ["零食测评", "办公室零食", "追剧必备", "代购零食", "健康零食", "自制零食", "地方特产", "巧克力品鉴", "坚果推荐", "茶饮搭配", "网红零食", "减脂零食"],
    "粮油调料": ["厨房必备", "食用油科普", "酱油测评", "调料搭配", "五谷杂粮", "面粉选择", "醋的妙用", "辣酱推荐", "烘焙原料", "进口调料", "传统工艺", "控盐减油"],
    "医疗保健": ["健康科普", "体检指南", "保健品真相", "家庭药箱", "慢病管理", "睡眠改善", "眼部健康", "口腔护理", "骨骼健康", "免疫力提升", "中老年保健", "办公族健康"],
    "家用器械": ["按摩器测评", "血压计选购", "家用理疗", "康复器械", "体重秤推荐", "雾化器", "制氧机", "护腰护膝", "足浴盆", "颈椎枕", "热敷仪", "艾灸仪"],
    "中医养生": ["节气养生", "药膳食疗", "穴位保健", "泡脚方子", "艾灸入门", "体质调理", "四季进补", "经络按摩", "茶饮养生", "情志调养", "睡眠养生", "古方今用"],
}

# --- 18个品类专属人设池 ---
PERSONA_POOL = {
    "图书教育": ["通勤看书的上班族", "全职妈妈", "大三学生", "中年书虫", "职场新人", "退休教师", "程序员"],
    "家用日常": ["独居女生", "新婚小两口", "三口之家的妈妈", "租房党", "家居博主", "洁癖强迫症", "懒人代表"],
    "精品服饰": ["小个子女生155cm", "微胖姐姐130斤", "职场白领", "大学女生", "文艺青年", "穿搭小白", "中年阿姨也爱美"],
    "食品生鲜": ["广东吃货", "健身达人", "厨房小白", "家有俩娃的宝妈", "独居打工人", "退休大爷", "减脂期的我"],
    "数码家电": ["数码发烧友", "普通上班族", "大学生", "设计师", "游戏玩家", "科技小白", "家电维修老师傅"],
    "美妆个护": ["干皮星人", "油痘肌", "成分党", "学生党穷鬼", "30+抗老选手", "美妆博主", "敏感肌十年"],
    "母婴用品": ["新手妈妈", "二胎宝妈", "全职爸爸", "90后辣妈", "育儿嫂转正", "龙凤胎妈妈", "高龄产妇"],
    "运动户外": ["跑步新手", "健身3年老手", "周末登山客", "瑜伽爱好者", "骑行通勤族", "带娃露营党", "办公室久坐族"],
    "鞋靴箱包": ["鞋控女生", "通勤族", "旅行达人", "球鞋收藏家", "学生党", "职场新人", "中年品质追求者"],
    "汽车用品": ["新手女司机", "老司机10年驾龄", "自驾游爱好者", "网约车师傅", "宝爸用车族", "改装入门小白", "节油达人"],
    "珠宝配饰": ["首饰控女生", "珠宝设计师", "送礼纠结星人", "古风爱好者", "极简主义者", "刚订婚的小仙女", "中年优雅女性"],
    "宠物用品": ["养了两只猫的独居女生", "金毛铲屎官", "异宠爱好者", "第一次养狗的小白", "多猫家庭", "宠物店老板", "流浪动物救助者"],
    "鲜花园艺": ["阳台党", "多肉新手", "退休后的花痴阿姨", "办公室绿植达人", "小院子业主", "花艺师在读", "佛系养花人"],
    "零食干货": ["零食控女大学生", "办公室摸鱼党", "减肥又嘴馋星人", "带娃选零食的妈妈", "代购零食爱好者", "健康零食追求者", "地方特产收集者"],
    "粮油调料": ["家庭主厨", "烘焙爱好者", "养生达人", "厨艺新手", "餐饮从业者", "有机食品追求者", "传统饮食文化爱好者"],
    "医疗保健": ["关注父母健康的上班族", "慢病患者家属", "健康管理师", "久坐办公族", "失眠多年的人", "刚做完体检的打工人", "中老年保健达人"],
    "家用器械": ["颈椎不好的程序员", "膝盖受过伤的跑者", "给爸妈买礼物的子女", "产后恢复中的宝妈", "理疗师", "老年人自用", "健身后恢复爱好者"],
    "中医养生": ["中医爱好者", "湿气重的南方人", "失眠调理中", "体寒怕冷的女生", "亚健康上班族", "跟奶奶学养生的90后", "刚入门的养生小白"],
}

# --- 通用变量池 (所有品类共用) ---
STYLE_POOL = ["轻松日常", "走心感悟", "干货总结", "故事叙述", "吐槽", "文艺清新", "接地气", "争议讨论"]
STRUCTURE_POOL = ["纯叙述体", "小标题分段", "问答式", "倒叙", "对比式", "清单体", "对话体", "日记体"]
TITLE_STYLE_POOL = ["疑问式", "数字式", "故事式", "反转式", "情感式", "实用式"]
TIME_HOOK_POOL = ["春天万物复苏", "夏天炎热", "秋天凉爽", "冬天寒冷", "周末午后", "深夜睡不着",
                  "年初立flag", "年底总结", "发工资后", "搬家整理", "节假日宅家", "下班回家后"]


# ============================================================
# Prompt 构建器
# ============================================================

class PromptBuilder:
    """从6维变量池随机抽取组合，拼装完整Prompt"""

    @staticmethod
    def build(category: str, topic_keyword: str = "", product_name: str = "") -> dict:
        """
        返回:
          sys_prompt, user_prompt, polish_sys, combo_id
        """
        angle = random.choice(ANGLE_POOL.get(category, ["综合分享"]))
        persona = random.choice(PERSONA_POOL.get(category, ["普通用户"]))
        style = random.choice(STYLE_POOL)
        structure = random.choice(STRUCTURE_POOL)
        title_style = random.choice(TITLE_STYLE_POOL)
        time_hook = random.choice(TIME_HOOK_POOL)

        # 组合ID
        a_idx = ANGLE_POOL.get(category, []).index(angle) if angle in ANGLE_POOL.get(category, []) else 0
        p_idx = PERSONA_POOL.get(category, []).index(persona) if persona in PERSONA_POOL.get(category, []) else 0
        combo_id = f"A{a_idx}P{p_idx}S{STYLE_POOL.index(style)}T{TITLE_STYLE_POOL.index(title_style)}"

        extra = ""
        if topic_keyword:
            extra += f"\n- 主题关键词：{topic_keyword}"
        if product_name:
            extra += f"\n- 重点产品：{product_name}"

        sys_prompt = f"""# 最高优先级指令
你正在为百家号【{category}】品类账号写文章。
文章内容必须100%围绕【{category}】展开，这是不可违反的硬性要求。

## 品类约束（极其重要，违反则文章作废）
- 文章的主题、场景、提到的产品/品牌/知识点，都必须属于【{category}】领域
- 文章中必须至少出现3个与【{category}】直接相关的具体产品名、品牌名或专业术语
- 禁止跑题！不要写成个人成长、时间管理、心灵鸡汤等与品类无关的内容
- 不要写成广告文或推销文，这是纯内容分享

## 你的身份设定
你是一个{persona}，用自己的真实经历和感受来写这篇关于【{category}】的文章。

## 本次创作参数
- 内容品类：{category}
- 切入角度：{angle}
- 写作风格：{style}
- 文章结构：{structure}
- 标题风格：{title_style}
- 时间/场景背景：{time_hook}

## 写作要求（10条具体规则）
1. 字数800-1200字
2. 纯内容文章，绝对不带任何商品推广、购买链接、价格信息、店铺名
3. 必须包含具体的、真实存在的产品名/品牌名（且必须是{category}领域的）
4. 像真人分享，有个人经历、具体场景、真实情感
5. 不要出现"作为一个xxx"、"今天给大家分享"、"废话不多说"等套话
6. 可以有口语化表达、省略号、感叹词
7. 开头3秒抓住读者
8. 标题15-30字，有吸引力但不标题党
9. 适当加粗1-2个重点句子
10. 结尾引发互动（提问、征集经验等）
{f'''
## 额外要求{extra}''' if extra else ''}

## 输出格式
标题：xxx

正文内容..."""

        user_prompt = f"""请以"{persona}"的身份，围绕【{category}】品类，从"{angle}"的角度，用"{style}"的风格，写一篇百家号文章。

记住：
- 品类是【{category}】，所有内容必须与此相关
- 你的人设是{persona}
- 文章结构用{structure}
- 标题风格用{title_style}
- 融入"{time_hook}"的时间/场景背景
- 必须出现至少3个{category}领域的真实品牌名或产品名

现在开始写："""

        polish_sys = f"""你是文章润色专家。当前品类：【{category}】

## 品类一致性检查（最高优先级）
先检查文章是否围绕【{category}】品类展开。如果文章与该品类严重不符，你必须完全重写一篇围绕【{category}】的文章，而不是只做润色。

## 润色原则
1. 去除AI痕迹：删掉机械化过渡词（"首先...其次...最后..."）、排比句、空话
2. 增加真人感：加入口语化表达（"说真的"、"emmm"、"哈哈"、"真的绝了"），段落长短有变化
3. 保留核心内容：产品名/品牌名保留，不要删掉具体细节
4. 百家号适配：标题15-30字，正文800-1200字，结尾互动，加粗1-2个金句
5. 不要加任何商品链接、价格、店铺名等推广内容
6. 确保文章中至少有3个{category}领域的真实品牌名/产品名

## 输出格式
标题：xxx

正文内容..."""

        log.info(f"  变量组合: 角度={angle}, 人设={persona}, 风格={style}, "
                 f"结构={structure}, 标题={title_style}, 场景={time_hook}")
        log.info(f"  combo_id: {combo_id}")

        return {
            "sys_prompt": sys_prompt,
            "user_prompt": user_prompt,
            "polish_sys": polish_sys,
            "combo_id": combo_id,
        }


# ============================================================
# 百度 AIGC 调用器 (复用百家号cookie, 无需额外API Key)
# ============================================================

class BaiduAIGC:
    """百度AIGC接口 - 使用百家号同一session"""

    def __init__(self, session: requests.Session, model: str = "ds_v3"):
        self.session = session
        self.model = model

    def generate(self, prompt: str) -> str:
        """
        调用百度AIGC接口生成文章。
        接口只接受单条query，所以调用者需要把system+user prompt合并后传入。
        返回生成的文本内容(可能含HTML标签)。
        """
        # Step1: 创建对话
        resp = self.session.post(
            'https://aigc.baidu.com/aigc/saas/pc/v1/aiNews/createDialogue',
            headers={
                'Content-Type': 'application/json',
                'Origin': 'https://aigc.baidu.com',
                'Referer': 'https://aigc.baidu.com/aiArticle',
            },
            json={}
        )
        resp.raise_for_status()
        dialogue_id = resp.json().get('data', {}).get('dialogue_id', '')
        if not dialogue_id:
            raise Exception(f"创建对话失败: {resp.text[:200]}")

        # Step2: 发送prompt, SSE流式读取
        resp = self.session.post(
            'https://aigc.baidu.com/aigc/saas/pc/v1/aiNews/chat',
            headers={
                'Accept': 'text/event-stream',
                'Content-Type': 'application/json',
                'Origin': 'https://aigc.baidu.com',
                'Referer': f'https://aigc.baidu.com/chat/{dialogue_id}',
            },
            json={
                "query": prompt,
                "enter_point": 1,
                "model": self.model,
                "dialogue_id": dialogue_id,
                "chat_type": 8
            },
            stream=True,
            timeout=(10, 180)
        )
        resp.raise_for_status()

        last_data = None
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.strip():
                continue
            raw = line.strip()
            if raw.startswith('data:'):
                raw = raw[5:].strip()
            try:
                parsed = json.loads(raw)
                last_data = parsed
                if parsed.get('data', {}).get('is_end') is True:
                    break
            except json.JSONDecodeError:
                continue

        if not last_data:
            raise Exception("百度AIGC未返回有效内容")

        content_obj = last_data.get('data', {}).get('content', {})
        title = content_obj.get('title', '')
        content = content_obj.get('content', '')

        # 百度AIGC返回的content可能带HTML，转成纯文本+markdown
        if '<p>' in content or '<h' in content:
            content = self._html_to_md(content)

        if title:
            return f"标题：{title}\n\n{content}"
        return content

    @staticmethod
    def _html_to_md(html: str) -> str:
        """简易HTML转Markdown"""
        text = html
        text = re.sub(r'<h[1-3][^>]*>(.*?)</h[1-3]>', r'## \1', text)
        text = re.sub(r'<strong>(.*?)</strong>', r'**\1**', text)
        text = re.sub(r'<b>(.*?)</b>', r'**\1**', text)
        text = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n', text)
        text = re.sub(r'<br\s*/?>', '\n', text)
        text = re.sub(r'<[^>]+>', '', text)  # 去掉剩余标签
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


# ============================================================
# 百家号发布器 (对齐 flower0wine 方案，无 Acs-Token)
# ============================================================

class BjhPublisher:
    """百家号API操作: Token获取 → 草稿 → 封面图 → 发布"""

    def __init__(self, cookie_str: str):
        self.session = requests.Session()
        self.cookie_str = cookie_str
        self.edit_token = None

        # 解析cookie
        for item in cookie_str.split(';'):
            item = item.strip()
            if '=' in item:
                k, v = item.split('=', 1)
                self.session.cookies.set(k.strip(), v.strip())

        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/133.0.0.0 Safari/537.36',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        })

    def refresh_token(self) -> bool:
        """从编辑页HTML提取JWT Token"""
        resp = self.session.get('https://baijiahao.baidu.com/builder/rc/edit')
        resp.raise_for_status()
        match = re.search(
            r'window\.__BJH__INIT__AUTH__\s*=\s*["\']([^"\']+)["\']',
            resp.text
        )
        if not match:
            log.error("Token获取失败，cookie可能已过期")
            return False
        self.edit_token = match.group(1)
        return True

    def fetch_categories(self) -> list:
        """
        调用 /pcui/article/cateusercms 获取百家号文章分类树
        返回: [{"label":"美食","value":"美食","children":[...]}]
        """
        try:
            resp = self.session.get(
                'https://baijiahao.baidu.com/pcui/article/cateusercms',
                headers={
                    'Accept': 'application/json, text/plain, */*',
                    'Referer': 'https://baijiahao.baidu.com/builder/rc/edit',
                },
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get('errno') == 0:
                return data.get('data', [])
        except Exception as e:
            log.warning(f"获取分类树失败: {e}")
        return []

    @staticmethod
    def match_category(product_category: str, category_tree: list) -> tuple:
        """
        根据商品品类自动匹配百家号文章分类(一级+二级)
        返回: (cate_d1, cate_d2)  如 ("美食", "美食教学")
        """
        # 精确映射: 18个商品品类 → 百家号文章分类
        CATEGORY_MAP = {
            "图书教育": ("教育", "兴趣学习"),
            "家用日常": ("家居", "家居好物"),
            "精品服饰": ("时尚", "时尚潮流"),
            "食品生鲜": ("美食", "美食综合"),
            "数码家电": ("数码", "数码综合"),
            "美妆个护": ("时尚", "时尚综合"),
            "母婴用品": ("母婴育儿", "母婴用品"),
            "运动户外": ("体育", "健身"),
            "鞋靴箱包": ("时尚", "时尚潮流"),
            "汽车用品": ("汽车", "用车养车"),
            "珠宝配饰": ("时尚", "时尚综合"),
            "宠物用品": ("宠物", "宠物用品"),
            "鲜花园艺": ("家居", "家居综合"),
            "零食干货": ("美食", "美食测评"),
            "粮油调料": ("美食", "美食教学"),
            "医疗保健": ("健康养生", "健康综合"),
            "家用器械": ("健康养生", "健康综合"),
            "中医养生": ("健康养生", "养生活动"),
        }

        # 策略1: 精确映射 + 验证分类树
        if product_category in CATEGORY_MAP:
            d1, d2 = CATEGORY_MAP[product_category]
            for cat in category_tree:
                if cat['label'] == d1:
                    # 验证二级分类存在
                    for child in cat.get('children', []):
                        if child['label'] == d2:
                            log.info(f"  文章分类(精确): {d1} > {d2}")
                            return (d1, d2)
                    # 二级不存在，用该一级下的第一个二级
                    if cat.get('children'):
                        fallback_d2 = cat['children'][0]['label']
                        log.info(f"  文章分类(二级回退): {d1} > {fallback_d2}")
                        return (d1, fallback_d2)

        # 策略2: 关键词模糊匹配
        kw_map = {
            "图书": "教育", "教育": "教育", "家用": "家居", "服饰": "时尚",
            "食品": "美食", "生鲜": "美食", "数码": "数码", "家电": "数码",
            "美妆": "时尚", "母婴": "母婴育儿", "运动": "体育", "户外": "体育",
            "鞋": "时尚", "包": "时尚", "汽车": "汽车", "珠宝": "时尚",
            "宠物": "宠物", "鲜花": "家居", "园艺": "家居", "零食": "美食",
            "粮油": "美食", "调料": "美食", "医疗": "健康养生",
            "保健": "健康养生", "器械": "健康养生", "中医": "健康养生", "养生": "健康养生",
        }
        for kw, target_d1 in kw_map.items():
            if kw in product_category:
                for cat in category_tree:
                    if cat['label'] == target_d1 and cat.get('children'):
                        d2 = cat['children'][0]['label']
                        log.info(f"  文章分类(模糊): {target_d1} > {d2}")
                        return (target_d1, d2)

        # 策略3: 兜底
        log.info(f"  文章分类(兜底): 生活 > 生活技巧")
        return ("生活", "生活技巧")

    def save_draft(self, title: str, html_content: str) -> Optional[str]:
        """保存草稿，返回article_id"""
        resp = self.session.post(
            'https://baijiahao.baidu.com/pcui/article/save?callback=bjhdraft',
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://baijiahao.baidu.com',
                'Referer': 'https://baijiahao.baidu.com/builder/rc/edit',
                'Token': self.edit_token,
            },
            data={'title': title, 'content': html_content, 'type': 'news'}
        )
        text = resp.text
        if text.startswith('bjhdraft('):
            text = text[9:-1]
        data = json.loads(text)
        if data.get('errno') != 0:
            log.error(f"草稿保存失败: {data.get('errmsg', '')}")
            return None
        return str(data['ret']['article_id'])

    def get_cover_image(self, keyword: str, article_id: str) -> Optional[str]:
        """搜索正版图库 → 自动裁剪 → 返回封面URL"""
        try:
            resp = self.session.post(
                'https://baijiahao.baidu.com/aigc/bjh/pc/v1/picSearch',
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Origin': 'https://baijiahao.baidu.com',
                    'Referer': f'https://baijiahao.baidu.com/builder/rc/edit?type=news&article_id={article_id}',
                    'Token': self.edit_token,
                },
                data={'page_no': '0', 'keyword': keyword, 'page_size': '5'}
            )
            imglist = resp.json().get('data', {}).get('imglist', [])
            if not imglist:
                return None

            raw_url = imglist[0].get('bjh_watermark_url') or imglist[0].get('detail_url', '')

            # 自动裁剪
            resp2 = self.session.post(
                'https://baijiahao.baidu.com/materialui/picture/auto_cutting',
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Origin': 'https://baijiahao.baidu.com',
                    'Referer': f'https://baijiahao.baidu.com/builder/rc/edit?type=news&article_id={article_id}',
                    'Token': self.edit_token,
                },
                data={'org_url': raw_url, 'type': 'news', 'cutting_type': 'cover_image'}
            )
            new_url = resp2.json().get('data', {}).get('new_url', '')
            return new_url or raw_url
        except Exception as e:
            log.warning(f"封面图获取失败: {e}")
            return None

    def publish(self, article_id: str, title: str, html_content: str,
                cover_url: str = "", cate_d1: str = "", cate_d2: str = "") -> dict:
        """正式发布文章(含自动分类)"""
        if cover_url:
            cover_images_json = json.dumps([{
                "src": cover_url, "cropData": {}, "machine_chooseimg": 0,
                "isLegal": 0, "cover_source_tag": "text"
            }])
            cover_map_json = json.dumps([{"src": cover_url, "origin_src": cover_url}])
        else:
            cover_images_json = json.dumps([])
            cover_map_json = json.dumps([])

        plain = re.sub(r'<[^>]+>', '', html_content)
        abstract = plain[:120]

        form_data = {
            'type': 'news',
            'title': title,
            'content': html_content,
            'abstract': abstract,
            'len': str(len(html_content)),
            'activity_list[0][id]': 'ttv',
            'activity_list[0][is_checked]': '1',
            'activity_list[1][id]': 'reward',
            'activity_list[1][is_checked]': '1',
            'activity_list[2][id]': 'aigc_bjh_status',
            'activity_list[2][is_checked]': '0',
            'source_reprinted_allow': '0',
            'cover_image_source[wide_cover_image_source]': 'text',
            'abstract_from': '3',
            'isBeautify': 'false',
            'usingImgFilter': 'false',
            'cover_layout': 'one',
            'cover_images': cover_images_json,
            '_cover_images_map': cover_map_json,
            'cover_source': 'upload',
            'subtitle': '',
            'bjhtopic_id': '',
            'bjhtopic_info': '',
            'clue': '',
            'bjhmt': '',
            'order_id': '',
            'aigc_rebuild': '',
            'image_edit_point': json.dumps([
                {"img_type": "cover", "img_num": {"template": 0, "font": 0, "filter": 0, "paster": 0, "cut": 0, "any": 0}},
                {"img_type": "body", "img_num": {"template": 0, "font": 0, "filter": 0, "paster": 0, "cut": 0, "any": 0}}
            ]),
            'article_id': article_id,
        }

        # 自动填入文章分类
        if cate_d1:
            form_data['cate_user_cms[0]'] = cate_d1
        if cate_d2:
            form_data['cate_user_cms[1]'] = cate_d2

        resp = self.session.post(
            'https://baijiahao.baidu.com/pcui/article/publish',
            headers={
                'Accept': 'application/json, text/plain, */*',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://baijiahao.baidu.com',
                'Referer': f'https://baijiahao.baidu.com/builder/rc/edit?type=news&article_id={article_id}',
                'Token': self.edit_token,
            },
            data=form_data,
            params={'type': 'news', 'callback': 'bjhpublish'}
        )

        text = resp.text
        if text.startswith('bjhpublish('):
            text = text[11:-1]
        return json.loads(text)

    @staticmethod
    def md_to_html(md_text: str) -> str:
        """Markdown转百家号HTML"""
        parts = []
        for line in md_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            if line.startswith('### '):
                parts.append(f'<h3>{line[4:]}</h3>')
            elif line.startswith('## '):
                parts.append(f'<h3>{line[3:]}</h3>')
            elif line.startswith('# '):
                parts.append(f'<h2>{line[2:]}</h2>')
            else:
                line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
                parts.append(f'<p>{line}</p>')
        return ''.join(parts)


# ============================================================
# 解析LLM输出的标题和正文
# ============================================================

def parse_article(text: str) -> tuple:
    """从LLM输出中解析标题和正文，返回 (title, body_md)"""
    lines = text.strip().split('\n')
    title = ""
    body_start = 0

    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith('标题：') or s.startswith('标题:'):
            title = s.replace('标题：', '').replace('标题:', '').strip()
            body_start = i + 1
            break
        elif s.startswith('# ') and i == 0:
            title = s[2:].strip()
            body_start = 1
            break

    if not title:
        title = lines[0].strip()[:30]
        body_start = 1

    body = '\n'.join(lines[body_start:]).strip()
    return title, body


# ============================================================
# 单账号全流程
# ============================================================

def process_one_account(account: dict) -> dict:
    """
    处理单个账号: 选品类 → 生成 → 润色 → 发布
    使用百度AIGC接口(复用百家号cookie session)
    """
    name = account["name"]
    cookie = account["cookie"]
    categories = account["categories"]
    category = random.choice(categories)

    log.info(f"{'='*50}")
    log.info(f"开始处理: {name} | 品类: {category}")
    log.info(f"{'='*50}")

    result = {
        "account_name": name,
        "category": category,
        "success": False,
        "title": "",
        "article_id": "",
        "combo_id": "",
        "error": "",
    }

    try:
        # 初始化发布器 (同时复用session给AIGC)
        pub = BjhPublisher(cookie)
        aigc = BaiduAIGC(pub.session, model=BAIDU_AIGC_MODEL)

        # --- Step 1: 拼装Prompt ---
        log.info("Step 1: 构建Prompt...")
        prompts = PromptBuilder.build(category)
        result["combo_id"] = prompts["combo_id"]

        # --- Step 2: 百度AIGC生成初稿 ---
        # 百度AIGC只接受单条query，把 system + user prompt 合并
        log.info("Step 2: 百度AIGC生成初稿...")
        combined_prompt = f"""{prompts['sys_prompt']}

---
{prompts['user_prompt']}"""
        raw_article = aigc.generate(combined_prompt)
        title_raw, body_raw = parse_article(raw_article)
        log.info(f"  初稿: 《{title_raw}》 ({len(body_raw)} 字)")

        # --- Step 3: 百度AIGC润色降AI味 ---
        log.info("Step 3: 百度AIGC润色降AI味...")
        polish_prompt = f"""{prompts['polish_sys']}

---
请润色以下文章，去除AI味，增加真人感：

{raw_article}"""
        polished = aigc.generate(polish_prompt)
        title, body_md = parse_article(polished)
        log.info(f"  润色后: 《{title}》 ({len(body_md)} 字)")
        result["title"] = title

        # --- Step 4: 百家号发布 ---
        log.info("Step 4: 百家号发布...")
        html_content = BjhPublisher.md_to_html(body_md)

        # 获取Token
        if not pub.refresh_token():
            result["error"] = "Token获取失败"
            return result
        log.info("  ✅ Token OK")

        # 获取分类树 + 自动匹配文章分类
        category_tree = pub.fetch_categories()
        cate_d1, cate_d2 = pub.match_category(category, category_tree)

        # 保存草稿
        article_id = pub.save_draft(title, html_content)
        if not article_id:
            result["error"] = "草稿保存失败"
            return result
        result["article_id"] = article_id
        log.info(f"  ✅ 草稿保存: {article_id}")

        if RUN_MODE != "publish":
            log.info(f"  ⏸️  草稿模式，不发布")
            result["success"] = True
            result["error"] = "draft_mode"
            return result

        # 发布前刷新Token
        pub.refresh_token()

        # 搜索封面图
        cn_chars = re.findall(r'[\u4e00-\u9fff]+', title)
        keyword = cn_chars[0][:4] if cn_chars else category[:4]
        cover_url = pub.get_cover_image(keyword, article_id)
        if not cover_url:
            cover_url = pub.get_cover_image(category[:4], article_id) or ""
        if cover_url:
            log.info(f"  ✅ 封面图: {cover_url[:60]}...")
        else:
            log.warning("  ⚠️ 无封面图")

        # 正式发布
        pub_result = pub.publish(article_id, title, html_content, cover_url, cate_d1, cate_d2)
        errno = pub_result.get('errno', -1)

        if errno == 0:
            ret = pub_result.get('ret', {})
            result["success"] = True
            result["nid"] = ret.get('nid', '')
            log.info(f"  🎉 发布成功! nid={ret.get('nid', '')}")
        else:
            result["error"] = pub_result.get('errmsg', f'errno={errno}')
            log.error(f"  ❌ 发布失败: {result['error']}")

    except Exception as e:
        result["error"] = str(e)
        log.error(f"  ❌ 异常: {e}")

    return result


# ============================================================
# 主入口
# ============================================================

def main():
    start_time = time.time()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print(f"""
╔══════════════════════════════════════════════════╗
║  百家号全流程自动化 v5 — 纯 Python 版            ║
║  生成 → 润色 → 发布 | {now}   ║
║  模式: {RUN_MODE:<8s} | 账号数: {len(ACCOUNTS)}                    ║
╚══════════════════════════════════════════════════╝
    """)

    # 检查配置
    has_real_cookie = any("在这里填入" not in acc["cookie"] for acc in ACCOUNTS)
    if not has_real_cookie:
        log.error("❌ 请先填入至少一个账号的 cookie！")
        return

    # 使用百度AIGC接口，无需额外API Key，复用百家号cookie
    log.info(f"AI模型: 百度AIGC ({BAIDU_AIGC_MODEL})")
    random.seed(int(time.time() * 1000) % 2**31)

    # 逐账号处理
    results = []
    for i, account in enumerate(ACCOUNTS):
        if "在这里填入" in account["cookie"]:
            log.warning(f"跳过 {account['name']} (未配置cookie)")
            continue

        result = process_one_account(account)
        results.append(result)

        # 账号间延迟
        if i < len(ACCOUNTS) - 1:
            log.info(f"等待 {ACCOUNT_DELAY}s 后处理下一个账号...")
            time.sleep(ACCOUNT_DELAY)

    # 汇总
    elapsed = time.time() - start_time
    success = sum(1 for r in results if r["success"])
    failed = len(results) - success

    print(f"""
{'='*55}
 运行结果汇总
{'='*55}
 总耗时: {elapsed:.1f}s
 成功: {success} | 失败: {failed} | 总计: {len(results)}
{'-'*55}""")

    for r in results:
        status = "✅" if r["success"] else "❌"
        print(f" {status} {r['account_name']} | {r['category']} | "
              f"《{r['title'][:20]}》 | {r.get('combo_id', '')} | "
              f"{r.get('error', '')}")

    print(f"{'='*55}\n")

    # 输出JSON供后续使用
    log.info(f"完整结果JSON:")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
