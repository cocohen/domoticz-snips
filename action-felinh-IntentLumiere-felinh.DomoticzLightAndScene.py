#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import configparser
from hermes_python.hermes import Hermes
from hermes_python.ffi.utils import MqttOptions
from hermes_python.ontology import *

import io
import requests
import json
import jellyfish

import logging



MAX_JARO_DISTANCE = 0.4

CONFIGURATION_ENCODING_FORMAT = "utf-8"
CONFIG_INI = "config.ini"

class SnipsConfigParser(configparser.SafeConfigParser):
    print("#####SnipsConfigParser####")
    def to_dict(self):
        return {section : {option_name : option for option_name, option in self.items(section)} for section in self.sections()}


def read_configuration_file(configuration_file):
    print("#####read_configuration_file####")
    try:
        with io.open(configuration_file, encoding=CONFIGURATION_ENCODING_FORMAT) as f:
            conf_parser = SnipsConfigParser()
            conf_parser.readfp(f)
            return conf_parser.to_dict()
    except (IOError, configparser.Error) as e:
        return dict()

#RECUPERATION DES SCENE
def getSceneNames(conf,myListSceneOrSwitch):
    print("#####getSceneNames####")
    myURL="http://"+conf.get("secret").get("domoticz_ip")+':'+conf.get("secret").get("domoticz_port")+'/json.htm?type=scenes'
    response = requests.get(myURL)
    jsonresponse = response.json()#json.load(response)
    for scene in jsonresponse["result"]:
        myName=scene["Name"].encode('utf-8')
        myListSceneOrSwitch[(scene["idx"])] = {'Type':'switchscene','Name':myName}
    return myListSceneOrSwitch
# RECUPERATION DES SWITCHS
def getSwitchNames(conf,myListSceneOrSwitch):
    print("#####getSwitchNames####")
    myURL="http://"+conf.get("secret").get("domoticz_ip")+':'+conf.get("secret").get("domoticz_port")+'/json.htm?type=command&param=getlightswitches'
    response = requests.get(myURL)
    jsonresponse = response.json()#json.load(response)
    for sw in jsonresponse["result"]:
        myName=sw["Name"].encode('utf-8')
        if sw["Type"] == "Light/Switch":
            myListSceneOrSwitch[(sw["idx"])] = {'Type':'switchlight','Name':myName}

    print ("Light/Switches: ",myListSceneOrSwitch)
    return myListSceneOrSwitch


# RECUPERATION DES VOLETS
def getBlindsNames(conf,myListSceneOrSwitch):
    print("#####getBlindsNames####")
    myURL="http://"+conf.get("secret").get("domoticz_ip")+':'+conf.get("secret").get("domoticz_port")+'/json.htm?type=command&param=getlightswitches'
    response = requests.get(myURL)
    jsonresponse = response.json()#json.load(response)
    for sw in jsonresponse["result"]:
        myName=sw["Name"].encode('utf-8')
        if sw["Type"] == "Blinds":
            myListSceneOrSwitch[(sw["idx"])] = {'Type':'switchlight','Name':myName}
    print ("Blinds : ",myListSceneOrSwitch)
    return myListSceneOrSwitch
    
    
def BuildActionSlotList(intent):
    print("#####BuildActionsSlotList####")
    intentSwitchList=list()
    intentSwitchActionList=list()
    intentSwitchState='None' #by default if no action

    for (slot_value, slot) in intent.slots.items():
        if slot_value=="Action":
            #NLU parsing does not preserve order of slot, thus it is impossible to have different action ON and OFF in the same intent=> keep only the first:
            if slot[0].slot_value.value.value=="TurnOn":
                intentSwitchState='On'
            else :
                intentSwitchState='Off'   
        if slot_value=="ActionVolet":
            print("LA ",slot[0].slot_value.value.value)
            if slot[0].slot_value.value.value=="ouvrir":
                intentSwitchState='Off'
            else :
                intentSwitchState='On'   
            print(intentSwitchState)
 
        if slot_value=="Interrupteur" or slot_value=="PieceVolet":
            for slot_value2 in slot.all():
                intentSwitchList.append(slot_value2.value)

    if not intentSwitchState=='None':
        for mySwitch in intentSwitchList:
            intentSwitchActionList.append({'Name':mySwitch,'State':intentSwitchState})
    print ("intentswitchactionlist : ", intentSwitchActionList)
    return intentSwitchActionList

def curlCmd(idx,myCmd,myParam,conf):
    print("#####curlCmd####")
    command_url="http://"+conf.get("secret").get("domoticz_ip")+':'+conf.get("secret").get("domoticz_port")+'/json.htm?type=command&param='+myParam+'&idx='+str(idx)+'&switchcmd='+myCmd
    print("url", command_url)
    ignore_result = requests.get(command_url)

    
def ActionneEntity(name,action,myListSceneOrSwitch,conf):
    print("#####ActionneEntity####")
#derived from nice work of https://github.com/iMartyn/domoticz-snips
    lowest_distance = MAX_JARO_DISTANCE
    lowest_idx = 65534
    lowest_name = "Unknown"
    MyWord=name
    DomoticzRealName=""
    print("ActionneEntity: "+MyWord)
    for idx,scene in myListSceneOrSwitch.items():
#        print(str(scene['Name'],'utf-8'))
        distance = 1-jellyfish.jaro_distance(str(scene['Name'],'utf-8'), MyWord)
    #    print "Distance is "+str(distance)
        if distance < lowest_distance:
    #        print "Low enough and lowest!"
            lowest_distance = distance
            lowest_idx = idx
            lowest_name = scene['Name']
            lowest_Type= scene['Type']
    if lowest_distance < MAX_JARO_DISTANCE:
        #print (lowest_Type)
        DomoticzRealName=str(lowest_name,'utf-8')
        print("ActionneEntity: "+DomoticzRealName)
        #print(lowest_idx)
        curlCmd(lowest_idx,action,lowest_Type,conf)
        return True,DomoticzRealName
        #hermes.publish_end_session(intent_message.session_id, "j'allume "+lowest_name)
    else:
        return False,DomoticzRealName
    
# DESCRIPTION DES CALLBACKS EN FONCTION DES INTENTS
def subscribe_intent_callback(hermes, intentMessage):  
    print("#####subscribe_intent_callback####")
    conf = read_configuration_file(CONFIG_INI)
    print(conf)
    #a=IntentClassifierResult(intentMessage).intent_name
    hermes.publish_continue_session(intentMessage.session_id, "OK",["kiteskate:IntentLumiere","kiteskate:IntentVolets"])
    if len(intentMessage.slots.ActionVolet) > 0:
     print('---------Ordre Volets----------')
     action_wrapperBlinds(hermes, intentMessage, conf)
    else:
     print('---------Ordre Interrupteurs----------')
     action_wrapperOrdre(hermes, intentMessage, conf)

def action_wrapperBlinds(hermes, intentMessage, conf):
    print("#####action_wrapperBlinds####")
    myListBlinds=dict()
    myListBlinds= getBlindsNames(conf,myListBlinds)
    intentBlindsActionList=BuildActionSlotList(intentMessage)
    actionText=""
    myAction = True
    for intentBlindsAction in intentBlindsActionList:
        Match= ActionneEntity(intentBlindsAction["Name"],intentBlindsAction["State"],myListBlinds,conf)
        DomoticzRealName=Match[1]
        myAction=myAction and Match[0]
        print('ici',intentBlindsAction)
        if intentBlindsAction["State"]=="Off": 
            texte="J'ouvre "
        else:
            texte="Je ferme "
        actionText='{}, {} {}'.format(actionText,texte,str(DomoticzRealName))
    if myAction and len(intentBlindsActionList)>0: 
        hermes.publish_end_session(intentMessage.session_id, actionText)
    else:
        hermes.publish_end_session(intentMessage.session_id, "desolé, je n'ai pas compris")
 
 
#    if MyAction[0] : 
#        hermes.publish_end_session(intentMessage.session_id, result_sentence)
##    else:
#        print("pas d action")
#        hermes.publish_end_session(intentMessage.session_id, "desole, je ne pas m executer ")
    

def action_wrapperOrdre(hermes, intentMessage, conf):
    print("#####action_wrapperOrdre####")
    myListSceneOrSwitch=dict()
    myListSceneOrSwitch= getSceneNames(conf,myListSceneOrSwitch)
    myListSceneOrSwitch= getSwitchNames(conf,myListSceneOrSwitch)
    intentSwitchActionList=BuildActionSlotList(intentMessage)
    actionText=""
    myAction = True
    for intentSwitchAction in intentSwitchActionList:
        Match= ActionneEntity(intentSwitchAction["Name"],intentSwitchAction["State"],myListSceneOrSwitch,conf)
        DomoticzRealName=Match[1]
        myAction=myAction and Match[0]
        if intentSwitchAction["State"]=="On": 
            texte="J'allume"
        else:
            texte="J'éteins "
        actionText='{}, {} {}'.format(actionText,texte,str(DomoticzRealName))
    if myAction and len(intentSwitchActionList)>0: 
        hermes.publish_end_session(intentMessage.session_id, actionText)
    else:
        hermes.publish_end_session(intentMessage.session_id, "desolé, je n'ai pas compris")
    


if __name__ == "__main__":
    mqtt_opts = MqttOptions()
    with Hermes(mqtt_options=mqtt_opts) as h:
        h.subscribe_intent("kiteskate:IntentLumiere", subscribe_intent_callback)\
        .subscribe_intent("kiteskate:IntentVolets", subscribe_intent_callback)\
        .start()
