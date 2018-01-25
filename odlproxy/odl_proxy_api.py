import copy
import functools
import httplib
import os
import threading
import bottle
import re
import logging
import requests
import openstack2_api
import odl
import utils
from utils import get_logger
from bottle import post, get, delete, put
from bottle import request, response
import json
import time


__author__ = 'Massimiliano Romano'

logger = get_logger(__name__)

#_authorization = "Basic YWRtaW46YWRtaW4="
#_auth_secret = os.environ['ODLPROXY_AUTH_SECRET']
#_api_endpoint = "http://localhost:8001/"

#ENABLE HTTP LOGGING
httplib.HTTPConnection.debuglevel = 1
#logging.basicConfig()
#logging.getLogger().setLevel(logging.DEBUG)
req_log = logging.getLogger('requests.packages.urllib3')
req_log.setLevel(logging.DEBUG)
req_log.propagate = True

CONFIG_FILE_MAP_EXPERIMENTS = '/var/lib/odlproxy/odl_proxy-map_experiments.json'

def buildDefaultMapExperiment():
    mapTable = dict()
    mapTable[0] = { "table": [2,3,4]   , "assigned": False, "experiment_id" :"", "tenant_id" :""}
    mapTable[1] = { "table": [5,6,7]   , "assigned": False, "experiment_id" :"", "tenant_id" :""}
    mapTable[2] = { "table": [8,9,10]  , "assigned": False, "experiment_id" :"", "tenant_id" :""}
    mapTable[3] = { "table": [11,12,13], "assigned": False, "experiment_id" :"", "tenant_id" :""}
    mapTable[4] = { "table": [14,15,16], "assigned": False, "experiment_id" :"", "tenant_id" :""}
    return mapTable

#Search file Experiment Maps
def getMapExperiments():
    file = utils.readMapExperiments(CONFIG_FILE_MAP_EXPERIMENTS)
    if file:
        return file
    else:
        #Initilize file
        map = buildDefaultMapExperiment()
        utils.writeMapExperiments(map,CONFIG_FILE_MAP_EXPERIMENTS)
        return utils.readMapExperiments(CONFIG_FILE_MAP_EXPERIMENTS)

#Populate the experiments wirh value of _maptable
def populateExperimets():
    experiments = dict()
    for key, value in _mapTable.iteritems():
        if value["assigned"] == True:
            experiments[value["experiment_id"]] = {"tenant": value["tenant_id"], "flow_tables": value["table"]}
    return experiments

_mapTable = getMapExperiments()
logger.info("ODL PROXY API - READ JSON MAP EXPERIMENT %s",_mapTable )
_experiments = populateExperimets()
logger.info("ODL PROXY API - EXPERIMENT %s",_experiments )

@get('/SDNproxy/<token>')
def proxy_details_handler(token):
    """Handles experiment details"""
    logger.info("ODL PROXY - GET /SDNproxy")

    if check_auth_header(request.headers):
        if token in _experiments:
            response.headers['Content-Type'] = 'application/json'
            response.headers['Cache-Control'] = 'no-cache'
            logger.info("ODL PROXY - get /SDNproxy : %s", _experiments[token])
            return json.dumps(_experiments[token])
        else:
            raise bottle.HTTPError(404)
    else:
        logger.error("ODL PROXY - GET /SDNproxy : Auth-Secret error! 403")
        raise bottle.HTTPError(403, "Auth-Secret error!")

#Get port from OS by TenantId and InstanceID
def get_port(server_id,tenant_id):
    logger.debug("ODL PROXY - get_port - for tenant : " + str(tenant_id) + " and Instance ID : " + str(server_id))
    auth_url = os.environ['OS_AUTH_URL']
    user = os.environ['OS_USERNAME']
    password = os.environ['OS_PASSWORD']
    project_id = tenant_id

    logger.debug("----------------------------------------------------")
    logger.debug(" |             Connection to OPENSTAK             | ")
    logger.debug("----------------------------------------------------")
    logger.debug(" | ODL PROXY - auth_url  :" + str(auth_url))
    logger.debug(" | ODL PROXY - user      :" + str(user))
    logger.debug(" | ODL PROXY - password  :" + str(password))
    logger.debug(" | ODL PROXY - tenant_id :" + str(project_id))
    logger.debug("----------------------------------------------------")

    conn = openstack2_api.create_connection(auth_url, None, project_id, user, password)

    # Trasform object Generetor to List
    ports = list(openstack2_api.list_ports(conn, project_id))

    for port in ports:
        logger.debug("ODL PROXY - get_port: " + str(port.id))
        if server_id == port.device_id:
            return port

#Get all ports from OS by TenantId
def get_ports(tenant_id):
    logger.debug("ODL PROXY - get_ports for tenant :" + str(tenant_id))
    auth_url = os.environ['OS_AUTH_URL']
    user = os.environ['OS_USERNAME']
    password = os.environ['OS_PASSWORD']
    project_id = tenant_id

    logger.debug("----------------------------------------------------")
    logger.debug(" |             Connection to OPENSTAK             | ")
    logger.debug("----------------------------------------------------")
    logger.debug(" | ODL PROXY - auth_url  :" + str(auth_url))
    logger.debug(" | ODL PROXY - user      :" + str(user))
    logger.debug(" | ODL PROXY - password  :" + str(password))
    logger.debug(" | ODL PROXY - tenant_id :" + str(project_id))
    logger.debug("----------------------------------------------------")

    conn = openstack2_api.create_connection(auth_url, None, project_id, user, password)

    #Trasform object Generetor to List
    return list(openstack2_api.list_ports(conn, project_id))

#Assign the first three table free to experiment
def get_user_flowtables(tenant_id,experiment_id):
    logger.debug("ODL PROXY - get_user_flowtables for tenant :" + str(tenant_id) + "and experiment_id:" + str(experiment_id))
    count = 0
    for key, value in _mapTable.iteritems():
        if count<5:
            if value["assigned"] == False:
               value["assigned"] = True
               value["experiment_id"] = experiment_id
               value["tenant_id"] = tenant_id
               # Persistence

               return value["table"]
        else:
            msg = "ODL Proxy - Max concurrent Experiments reached - Max 5"
            logger.error(msg)
            return msg
        count = count + 1


    #odl = ODLDataRetriever()

    # Filtrare per le tabelle occupate per tenant

    #return odl.getTable()

    #flows_of_port = []
    #for port in ports:
        # print "port['id'] %d" % port.id
        #flows_of_port = odl.getFlows(port.id)
        # print "flows_of_port %d" % flows_of_port


def synchronized(wrapped):
    lock = threading.Lock()
    @functools.wraps(wrapped)
    def _wrap(*args, **kwargs):
        print "Calling '%s' with Lock %s" % (wrapped.__name__, id(lock))
        with lock:
            return wrapped(*args, **kwargs)
    return _wrap


def checkTenatExist(tenant_id):
    logger.debug("ODL PROXY - checkTenatExist for tenant :" + str(tenant_id))
    for key, value in _experiments.iteritems():
        if value['tenant'] == tenant_id:
            return True
        else:
            return False

#Get the table assigned by tenant
def getTableExperiments(tenant_id):
    logger.debug("ODL PROXY - getTableExperiments for tenant :" + str(tenant_id))
    for key, value in _experiments.iteritems():
        if value['tenant'] == tenant_id:
            return value['flow_tables']

#Delete the flow of VM
@synchronized
def deleteFlowFromVM(server_id,server_name,tenant_id):
    logger.info("ODL PROXY - START delele flow of VM : " + str(server_name) + ":" + str(server_id) + " of tenant id - " + str(tenant_id))
    try:
        if checkTenatExist(tenant_id):
            headers = {
                "Authorization": utils.encodeAuthorization(os.environ['ODL_USER'], os.environ['ODL_PASS']),
                "Content-Type": "application/json"
            }  # request.headers

            # Edit the flow on table 0 to first table on range
            nodes = odl.getAllNodes()

            tableExperiment = getTableExperiments(tenant_id)
            urlODL = "http://" + os.environ['ODL_HOST'] + ":" + os.environ['ODL_PORT'] + "/restconf/config/opendaylight-inventory:nodes/node/{NODE_ID}/table/{TABLE_ID}"
            urlODLflow = "http://" + os.environ['ODL_HOST'] + ":" + os.environ['ODL_PORT'] + "/restconf/config/opendaylight-inventory:nodes/node/{NODE_ID}/table/{TABLE_ID}/flow/{FLOW_ID}"

            for node in nodes:
                logger.debug("ODL PROXY - delele flow of VM - node :" + str(node.id))
                flowsTable0 = getFlowsTable(urlODL, node, 0, headers)
                if flowsTable0:
                    for flow in flowsTable0:
                        if "id" in flow:
                            flowId = flow['id']

                            # if flow is a flow custom
                            # Delete the ovveride flow in table 0
                            if server_id in flowId and tenant_id in flowId:
                                urlODLTable0 = urlODLflow.format(NODE_ID=node.id, TABLE_ID=0, FLOW_ID=flowId)
                                respTable0 = requests.delete(urlODLTable0, headers=headers)
                                utils.logFlow(str(respTable0.status_code) + " DELETE", str(flowId), None, None,server_id, server_name, node.id, None, 0, None)
                                #logger.info("ODL PROXY - "+str(respTable0.status_code) +" DELETE flow : " + str(flowId) + " on table - " + str(0) )

                flowsTableFirstExperiment = getFlowsTable(urlODL, node, tableExperiment[0], headers)
                if flowsTableFirstExperiment:
                    for flowFirstExperiment in flowsTableFirstExperiment:
                        if "id" in flowFirstExperiment:
                            flowId = flowFirstExperiment['id']
                            # if flow is a flow custom
                            # Delete the ovveride flow in experiment table
                            if server_id in flowId and tenant_id in flowId:
                                urlODLTableFirstExperiment = urlODLflow.format(NODE_ID=node.id, TABLE_ID=tableExperiment[0], FLOW_ID=flowId)
                                respFirstExperiment = requests.delete(urlODLTableFirstExperiment, headers=headers)
                                utils.logFlow(str(respFirstExperiment.status_code) + " DELETE", str(flowId), None, None, server_id, server_name, node.id, None, tableExperiment[0], None)
                                #logger.info("ODL PROXY - delele flow : " + str(flowId) + " on table - " + str(tableExperiment[0]) + " " + str(respFirstExperiment.status_code))

    except Exception as e:
        msg = "ODL Proxy - delele flow of VM" + str(e)
        logger.exception(msg)


#Create the flow of VM
@synchronized
def createFlowFromVM(server_id,server_name,tenant_id):
    logger.info("ODL PROXY - START create flow of VM : " + str(server_name) + ":" + str(server_id) + " of tenant id - " + str(tenant_id))
    try:
        if checkTenatExist(tenant_id):
            for x in range(0,3):
                createFlow = False
                logger.info("ODL PROXY - create flow - sleep 3 seconds")
                time.sleep(3)

                headers = {
                    "Authorization": utils.encodeAuthorization(os.environ['ODL_USER'], os.environ['ODL_PASS']),
                    "Content-Type": "application/json"
                }  # request.headers

                # Edit the flow on table 0 to first table on range
                nodes = odl.getAllNodes()
                #ports = get_ports(tenant_id)
                port = get_port(server_id, tenant_id)

                # Get flow on table 0
                urlODL = "http://" + os.environ['ODL_HOST'] + ":" + os.environ['ODL_PORT'] + "/restconf/config/opendaylight-inventory:nodes/node/{NODE_ID}/table/{TABLE_ID}"
                tableExperiment = getTableExperiments(tenant_id)

                for node in nodes:
                    logger.debug("ODL PROXY - create flow of VM - node :" + str(node.id))
                    flows = getFlowsTable(urlODL, node, 0, headers)
                    flowsFiltered = filterFlow(flows,type,node,tenant_id)

                    for flowOriginal in flowsFiltered["flowsOriginal"]:
                        if port.id in flowOriginal["flow-name"]:
                            if checkPortInFlows(flowsFiltered["flowsCustom"],port.id):
                                #logger.info("Flow : "+ flowsFiltered["flowsCustom"]["flow-name"] +" already overwritten")
                                print "Flow already overwritten"
                            else:
                                #create the custom Flow
                                createFlow = True
                                overrideFlow(flowOriginal, tableExperiment, tenant_id, port, urlODL, headers, node.id,server_id,server_name)

                if not createFlow:
                    if x==3:
                        logger.error("STOP RETRYING TO CREATE FLOW FOR VM : " + str(server_id) + " NO FLOW CREATED")
                        break
                    else:
                        logger.info( str(x+1) + " RETRYING TO CREATE FLOW FOR VM : " + str(server_id))
                else:
                    break

    except Exception as e:
        msg = "ODL Proxy - Exception on create flow of VM :" + str(server_id) + " - " + str(e)
        logger.exception(msg)


def checkPortInFlows(flows,portId):
    founded = False
    for flowCustom in flows:
        if portId in flowCustom["flow-name"]:
            logger.info("Flow : " + flowCustom["flow-name"] + " already overwritten")
            founded = True
            break
        else:
            founded = False
    return founded

def filterFlow(flows,type,node,tenant_id):
    flowsCustom = []
    flowsOriginal = []

    for flow in flows:
        #If start with tenat is custom
        if flow["flow-name"].startswith(tenant_id):
            flowsCustom.append(flow);
            logger.debug("FilterFlow flowsCustom %s", flow["flow-name"])
        # If contains node is odl
        nodeId = node.id
        id = nodeId.split(":")[1]
        if id in flow["flow-name"]:
            flowsOriginal.append(flow);
            logger.debug("FilterFlow flowsOriginal %s", flow["flow-name"])

    if len(flowsOriginal) > 0:

        logger.debug("FilterFlow flowsCustom %s", flowsCustom)
        logger.debug("FilterFlow flowsOriginal %s", flowsOriginal)
        return {
            "flowsCustom": flowsCustom,
            "flowsOriginal": flowsOriginal
        }
    else:
        logger.exception("ODL PROXY - EMPTY FLOWS ORIGINAL for node:port")
        raise Exception('ODL PROXY - EMPTY FLOWS ORIGINAL for node:port')

def findServerInPort(port):
    if port.device_owner == 'compute:nova':
        return port.device_id
    else:
        return None

@synchronized
@post('/SDNproxySetup')
def proxy_creation_handler():
    logger.debug("ODL PROXY - POST /SDNproxySetup")

    """Handles experiment/proxy creation
      request:
      {
        "experiment_id": "a5cfaf1e81f35fde41bef54e35772f2b",
        "tenant_id": "fed0b52c7e034d5785880613e78d4411"
      }
      response:
      {
        "endpoint_url": "http:/foo.bar",
        "user-flow-tables": [10,11,12,13,14,15]
      }
    """
    try:
        # parse input data
        try:
            data = request.json
            logger.debug("JSON: %s" % request.json)
        except Exception as e:
            logger.exception(e)
            raise ValueError(e)

        if data is None:
            logger.error("ODL Proxy - Cant read json request")
            raise ValueError

        experiment_id = data['experiment_id']
        tenant_id = data["tenant_id"]

        # check for existence
        if experiment_id in _experiments:
            response.status = 500
            msg ="ODL Proxy - Duplicate experiment!"
            logger.error(msg)
            return msg

        elif len(_experiments) > 0 : #Check if the tenant already associated
            if checkTenatExist(tenant_id):
                response.status = 500
                msg = "ODL Proxy - Tenant: " + tenant_id + " already associated!"
                logger.error(msg)
                return msg

        #Edit the flow on table 0 to first table on range
        nodes = odl.getAllNodes()
        ports = get_ports(tenant_id)

        # Get flow on table 0
        urlODL = "http://" + os.environ['ODL_HOST'] + ":" + os.environ['ODL_PORT'] + "/restconf/config/opendaylight-inventory:nodes/node/{NODE_ID}/table/{TABLE_ID}"
        # Assign the first three table free to experiment
        tableExperiment = get_user_flowtables(tenant_id, experiment_id)

        headers = {
            "Authorization": utils.encodeAuthorization(os.environ['ODL_USER'], os.environ['ODL_PASS']),
            "Content-Type": "application/json"
        }  # request.headers

        for node in nodes:
            logger.debug("ODL PROXY - POST /SDNproxySetup node : " + str(node.id))
            try:
                flows = getFlowsTable(urlODL, node,0,headers)
                for flow in flows:
                    if 'id' in flow:
                        for port in ports:
                            logger.debug("ODL PROXY - POST /SDNproxySetup port :" + str(port.id))
                            if port.id in flow['id']:
                                serverId = findServerInPort(port)
                                if serverId is not None:
                                    overrideFlow(flow, tableExperiment, tenant_id, port, urlODL, headers,node.id,serverId,None)

            except Exception as e:
                response.status = 400
                msg = "ODL Proxy - POST /SDNproxySetup : " + str(e)
                logger.exception(msg)
                return json.dumps({"msg": msg})

        # Persistence
        utils.writeMapExperiments(_mapTable, CONFIG_FILE_MAP_EXPERIMENTS)
        _experiments[experiment_id] = {"tenant": tenant_id, "flow_tables": tableExperiment}

        response.headers['Content-Type'] = 'application/json'
        response.headers['Cache-Control'] = 'no-cache'

        url = "http://{HOSTNAME}:8001/".format(HOSTNAME=os.environ["ODLPROXY_PUBLIC_IP"])
        strTables = ','.join(str(e) for e in _experiments[experiment_id]["flow_tables"])
        logger.info("ODL PROXY - /SDNproxySetup return table :" + strTables  + " for Experiment id :" + str(experiment_id) )
        logger.debug("ODL PROXY - /SDNproxySetup %s", _experiments)
        return json.dumps(
            {"user-flow-tables": _experiments[experiment_id]["flow_tables"], "endpoint_url": url})

    except Exception as e:
        logger.exception("ODL PROXY - POST /SDNproxySetup : " + str(e) )
        response.status = 500

def getIpfromPort(port):
    ip = []
    for ips in port.fixed_ips:
        if 'ip_address' in ips:
            ip.append(ips['ip_address'])
    return ip

#Build json for ovverideFlow
#1 override flow from 0 to first table of experiments
#2 override flow from first table of experiments to table 17
def overrideFlow(flow,tableExperiment,tenant_id,port,urlODL,headers,nodeId,instanceId,server_name):
    logger.debug("ODL PROXY - overrideFlow : flow :" + str(flow['flow-name']) + " - tenant_id : " + str(tenant_id) + " - port : " + str(port.id) +  " - nodeId : " + str(nodeId) + " - instanceId : " + str(instanceId) )

    #Edit Flow
    flow1Put = copy.deepcopy(flow)
    flow2Put = copy.deepcopy(flow)

    portOvs = getPortOVS(flow)
    portIp = getIpfromPort(port)
    # Prepare the first json request
    strdata = builDataFirstPut(flow, flow1Put, tableExperiment, tenant_id, port,portOvs,instanceId)

    if strdata:
        urlTable1 = urlODL.format(NODE_ID = nodeId, TABLE_ID= '0')
        urlODLput1 = urlTable1 + '/flow/' + flow1Put['flow-name']
        resp1 = requests.put(urlODLput1, data=strdata, headers=headers)

        #logger.debug("ODL PROXY - resp.status_code " + str(resp1.status_code))
        #logger.debug("ODL PROXY - resp.headers " + str(resp1.headers))
        #logger.debug("ODL PROXY - resp.text " + str(resp1.text))

        if resp1.status_code == 200 or resp1.status_code == 201:

            utils.logFlow(str(resp1.status_code) + " PUT", flow1Put['flow-name'], port.id, portIp, instanceId, server_name, nodeId, portOvs, 0, tableExperiment[0])
            #logger.info("ODL PROXY - overrideFlow - flow " + flow1Put['flow-name'] + " in table " + str(tableExperiment) + " " + str(resp1.status_code))

            # Prepare the second json request
            strdata2 = builDataSecondPut(flow, flow2Put, tableExperiment, tenant_id,port, portOvs,instanceId)
            urlTable2 =  urlODL.format(NODE_ID = nodeId, TABLE_ID=str(tableExperiment[0]))
            urlODLput2 = urlTable2 + '/flow/' + flow2Put['flow-name']
            resp2 = requests.put(urlODLput2, data=strdata2, headers=headers)

            utils.logFlow(str(resp2.status_code) + " PUT", flow2Put['flow-name'], port.id, portIp, instanceId, server_name, nodeId, portOvs, tableExperiment[0], 17)
            #logger.info("ODL PROXY - overrideFlow - flow " + flow2Put['flow-name'] + " in table " + str(  tableExperiment[0]) + " " + str(resp2.status_code))

            #logger.debug("ODL PROXY - resp.status_code " + str(resp2.status_code))
            #logger.debug("ODL PROXY - resp.headers " + str(resp2.headers))
            #logger.debug("ODL PROXY - resp.text " + str(resp2.text))


# Return the flow of table
def getFlowsTable(urlODL, node,table,headers):
    logger.debug("ODL PROXY - getFlowsTable : - node : " + str(node.id) + " - table : " + str(table) )
    urlODL = urlODL.format(NODE_ID=node.id, TABLE_ID= table)
    resp = requests.get(urlODL, headers=headers)
    dataj = resp.json()
    if 'flow-node-inventory:table' in dataj:
        tables = dataj['flow-node-inventory:table']
        return tables[0]['flow']


#Deprecated
def getFlowsTable0(urlODL, node,headers):
    resp = requests.get(urlODL, headers=headers)
    dataj = resp.json()
    if 'flow-node-inventory:table' in dataj:
        tables = dataj['flow-node-inventory:table']
        return tables[0]['flow']

#Name convection for id and name to overrideflow
#TenantId_table_id Port OVS _ Port Id OS _ Instance ID
#Instance Id need to delete ovverride flow
def buildStringFlow(tenant_id,table,portOvs,portId,instanceId):
    if instanceId is None:
       return tenant_id + '_' + str(table) + '_' + portOvs + '_' + portId
    else:
       return tenant_id + '_' + str(table) + '_' + portOvs + '_' + portId + '_' + instanceId

#Create Json to second ovverride flow from experimeter table to table 17
def builDataSecondPut(flow, flow2Put, tableExperiment, tenant_id, port,portOvs,instanceId):

    id_name_flow = buildStringFlow(tenant_id, 17, portOvs, port.id, instanceId)
    logger.debug("ODL PROXY - builDataSecondPut flow : " + id_name_flow + " in table : " + str(tableExperiment[0]))

    flow2Put['priority'] = flow['priority'] * 10
    flow2Put['id'] = id_name_flow
    flow2Put['flow-name'] = id_name_flow
    flow2Put['table_id'] = tableExperiment[0]
    flow2Put = setGoToTAble(flow2Put, 17)

    if 'in-port' in flow2Put['match']:
        del flow2Put['match']['in-port']

    writeMetaData = getWriteMetaData(flow2Put)
    flow2Put = deleteWriteMetaData(flow2Put)
    flow2Put['match'] = writeMetaData

    flow2TagWrapper = dict()
    flow2TagWrapper["flow-node-inventory:flow"] = [flow2Put]

    flow2TagWrapper = dict()
    flow2TagWrapper["flow-node-inventory:flow"] = [flow2Put]

    return json.dumps(flow2TagWrapper, ensure_ascii=False)

#Create Json to second ovverride flow from table 0 to experimeter table
def builDataFirstPut(flow,flow1Put,tableExperiment,tenant_id,port,portOvs,instanceId):

    tableDestination = getGoToTAble(flow, tableExperiment[0])

    # At the moment only in case table 17 rewrite the flow
    if tableDestination == 17:
        flow1Put = setGoToTAble(flow1Put, tableExperiment[0])
    else:
        logger.error('ODL PROXY - IN FLOW ' + str(flow['id']) + ' GO TO TABLE NOT 17')
        return None

    id_name_flow = buildStringFlow(tenant_id,tableExperiment[0],portOvs,port.id,instanceId)
    logger.debug("ODL PROXY - builDataFirstPut flow : " + id_name_flow + " in table : " + str(0))

    flow1Put['priority'] = flow['priority'] * 10
    flow1Put['id'] = id_name_flow
    flow1Put['flow-name'] = id_name_flow

    flow1TagWrapper = dict()
    flow1TagWrapper["flow-node-inventory:flow"] = [flow1Put]

    return json.dumps(flow1TagWrapper, ensure_ascii=False)

def getPortOVS(flow):
    if 'match' in flow:
        match = flow['match']
        if 'in-port' in match:
            return match['in-port'].split(':')[2]


def getGoToTAble(flow,tables):
    if 'instructions' in flow:
        flow_node_instructions = flow['instructions']
        if 'instruction' in flow_node_instructions:
            instructions = flow_node_instructions['instruction']
            for instruction in instructions:
                if 'go-to-table' in instruction:
                    goToTable = instruction['go-to-table']
                    return goToTable['table_id']

    else:
        return -1

def setGoToTAble(flow,numberTable):
    if 'instructions' in flow:
        flow_node_instructions = flow['instructions']
        if 'instruction' in flow_node_instructions:
            instructions = flow_node_instructions['instruction']
            for instruction in instructions:
                if 'go-to-table' in instruction:
                    goToTable = instruction['go-to-table']
                    goToTable['table_id'] = numberTable
    return flow

def getWriteMetaData(flow):
    if 'instructions' in flow:
        flow_node_instructions = flow['instructions']
        if 'instruction' in flow_node_instructions:
            instructions = flow_node_instructions['instruction']
            for instruction in instructions:
                if 'write-metadata' in instruction:
                    del instruction['order']
                    inst = dict()
                    inst['metadata'] = instruction['write-metadata']
                    return inst

def deleteWriteMetaData(flow):
    if 'instructions' in flow:
        flow_node_instructions = flow['instructions']
        if 'instruction' in flow_node_instructions:
            instructions = flow_node_instructions['instruction']
            count = 0
            for instruction in instructions:
                if 'write-metadata' in instruction:
                    del flow['instructions']['instruction'][count]
                count = count + 1
    return flow

#Delete Experiment
@synchronized
@delete('/SDNproxy/<token>')
def delete_handler(token):
    """delete the mapping between experiment-token and tenant id
    :returns  200 but no body
    """
    logger.info("ODL PROXY - DELETE /SDNproxy")

    try:
        if check_auth_header(request.headers):

            # check the headears parameter
            accept = request.headers.get('Accept')
            if not accept:
                accept = 'application/json'

            #        x = _experiments[token]
            #        del _experiments[token]

            for key, value in _experiments.iteritems():
                if key == token :
                    tenant_id = value["tenant"]

                    if _experiments.pop(token, None) is None:
                        response.status = 404
                        msg = "Experiment not found!"
                        logger.error(msg)
                        return json.dumps({"msg": msg})

                    else:

                        #Clear the table assigned to experimenter
                        for key, value in _mapTable.iteritems():
                            if value["experiment_id"] == token:
                                value["assigned"] = False
                                value["experiment_id"] = ""
                                value["tenant_id"] = ""

                                # Persistence
                                utils.writeMapExperiments(_mapTable,CONFIG_FILE_MAP_EXPERIMENTS)

                                tablesExperiment = copy.deepcopy(value["table"])
                                tablesExperiment.append(0)  # Add Table 0 for remove overide flow
                                break

                        headers = {'Accept': accept,
                                   "Authorization": utils.encodeAuthorization(os.environ['ODL_USER'], os.environ['ODL_PASS'])
                                   }

                        nodes = odl.getAllNodes()
                        for node in nodes:
                            logger.debug("ODL PROXY - DELETE /SDNproxy node :" + str(node.id))
                            id = node.id

                            for table in tablesExperiment :
                                urlODL = "http://" + os.environ['ODL_HOST'] + ":" + os.environ['ODL_PORT'] + "/restconf/config/opendaylight-inventory:nodes/node/{NODE_ID}/table/{TABLE_ID}"
                                urlODL = urlODL.format(NODE_ID=node.id, TABLE_ID=table)
                                if table == 0:
                                    respGet = requests.get(urlODL, headers=headers)
                                    dataj= respGet.json()
                                else:
                                    # Delete override flow in tables assigned to experiment
                                    respDelete = requests.delete(urlODL, headers=headers)
                                    logger.info("ODL PROXY /SDNproxy - " + str(respDelete.status_code) + " DELETE TABLE " + str(table) + " in NODE : " + str(node.id))

                            # Delete override flow in table 0
                            if 'flow-node-inventory:table' in dataj:
                                tables = dataj['flow-node-inventory:table']
                                for table in tables:
                                    if 'flow' in table:
                                        flows = table['flow']
                                        for flow in flows:
                                            if 'id' in flow:
                                                idFlow = flow['id']
                                                for tab in tablesExperiment:
                                                    nameFlow = tenant_id + "_" + str(tab)
                                                    if idFlow.startswith(nameFlow):
                                                        urlODL = "http://" + os.environ['ODL_HOST'] + ":" + os.environ['ODL_PORT'] + "/restconf/config/opendaylight-inventory:nodes/node/{NODE_ID}/table/{TABLE_ID}/flow/{FLOW_ID}"
                                                        urlODL = urlODL.format(NODE_ID=node.id, TABLE_ID=0, FLOW_ID=idFlow)
                                                        resp = requests.delete(urlODL, headers=headers)
                                                        utils.logFlow(str(resp.status_code) + " DELETE",idFlow, None, None, None,None, node.id, None, 0,None)

                        response.status = 200
                        msg = "ODL PROXY - DELETE /SDNproxy Experiment : " + token + " successfully deleted!"
                        logger.info(msg)
                        response.headers['Content-Type'] = 'application/json'
                        return json.dumps({"msg": msg})

        #AuthSecret Error
        else:
            logger.error("403 - Auth-Secret error!")
            raise bottle.HTTPError(403, "Auth-Secret error!")

    except Exception as e:
        logger.exception("ODL PROXY - DELETE /SDNproxy : " + str(e) )
        response.status = 500

def check_auth_header(headers):
    if "Auth-Secret" in headers.keys():
        auth_secret = headers.get("Auth-Secret")
        logger.debug("'Auth-Secret' header present! value: %s" % auth_secret)
        if auth_secret == os.environ['ODLPROXY_AUTH_SECRET']:
            return True
    return False

#Check the rest url
def check_url(url):

    # check the url
    flowregex = 'config/opendaylight-inventory:nodes/node/openflow:([0-9]*)/table/([0-9]*)/flow/([0-9]*)'
    tableregex = 'config/opendaylight-inventory:nodes/node/openflow:([0-9]*)/table/([0-9]*)'
    noderegex = 'config/opendaylight-inventory:nodes/node/openflow:([0-9]*)/'
    nodesregex = 'config/opendaylight-inventory:nodes'

    flow_search = re.search(flowregex, url, re.IGNORECASE)
    table_search = re.search(tableregex, url, re.IGNORECASE)
    node_search = re.search(noderegex, url, re.IGNORECASE)
    nodes_search = re.search(nodesregex, url, re.IGNORECASE)

    if flow_search:
        regexSearch = flow_search
        target = "flow"
    elif table_search :
        regexSearch = table_search
        target = "table"
    elif node_search:
        regexSearch = node_search
        target = "node"
    elif nodes_search:
        regexSearch = nodes_search
        target = "nodes"

    return {"regex": regexSearch, "target": target}


@delete('/restconf/<url:path>')
def deleteRestConf(url):
    logger.info("ODL PROXY - DELETE - /restconf/" + url)
    # check the headears parameter
    # TODO for headears
    try:
        token = request.headers.get('API-Token')  # Token is experiment id
        accept = request.headers.get('Accept')

        # check the headears parameter
        if not accept:
            accept = 'application/json'

        if not token:
            response.status = 400
            msg = "ODL Proxy - Bad Request! Header API-Token NOT FOUND"
            logger.error(msg)
            return json.dumps({"msg": msg})
        else:
            if token in _experiments.keys():
                tables = _experiments[token]["flow_tables"]
            else:
                response.status = 403
                msg = "ODL Proxy - Experiment not found!"
                logger.error(msg)
                return json.dumps({"msg": msg})

        # check the url
        jsonCheckUrl = check_url(url)
        urlODL = "http://" + os.environ['ODL_HOST'] + ":" + os.environ['ODL_PORT'] + "/restconf/" + url
        headers = {'Accept': accept,
                   "Authorization": utils.encodeAuthorization(os.environ['ODL_USER'], os.environ['ODL_PASS']),
                   "Content-Type": "application/json"
                   }  # request.headers

        # EXEC
        if jsonCheckUrl["target"] == "flow":
            tableId = int(jsonCheckUrl["regex"].group(2))
            if tableId in tables:
                resp = requests.delete(urlODL, headers=headers)
                logger.info("ODL PROXY - /restconf/" + url + " - " + str(resp.status_code) + " DELETE TABLE " + str(tableId))
        else:
            response.status = 403
            strTables = ','.join(str(e) for e in tables)
            msg = "ODL Proxy -DELETE - Forbidden can not delete " + jsonCheckUrl["target"]
            logger.error(msg)
            return json.dumps({"msg": msg})

        response.status = resp.status_code
        return resp.text

    except Exception as e:
        logger.exception("ODL PROXY - DELETE - /restconf/" + url + " - "+str(e) )
        response.status = 500

@get('/restconf/<url:path>')
def getRestConf(url):
    logger.info("ODL PROXY - GET - /restconf/" + url)
    # check the headears parameter
    try:
        # TODO for headears
        token = request.headers.get('API-Token')  # Token is experiment id
        accept = request.headers.get('Accept')

        # check the headears parameter
        if not accept:
            accept = 'application/json'

        if not token:
            response.status = 400
            msg = "ODL Proxy - Bad Request! Header API-Token NOT FOUND"
            logger.error(msg)
            return json.dumps({"msg": msg})
        else:
            if token in _experiments.keys():
                tables = _experiments[token]["flow_tables"]
            else:
                response.status = 403
                msg = "ODL Proxy - Experiment not found!"
                logger.error(msg)
                return json.dumps({"msg": msg})

        # check the url
        jsonCheckUrl = check_url(url)
        urlODL = "http://" + os.environ['ODL_HOST'] + ":" + os.environ['ODL_PORT'] + "/restconf/" + url
        headers = {'Accept': accept,
                   "Authorization": utils.encodeAuthorization(os.environ['ODL_USER'], os.environ['ODL_PASS']),
                   "Content-Type": "application/json"
                   }  # request.headers

        # EXEC
        if jsonCheckUrl["target"] == "flow" or jsonCheckUrl["target"] == "table":
            tableId = int(jsonCheckUrl["regex"].group(2))
            if tableId in tables:
                resp = requests.get(urlODL, headers=headers)
                logger.info("ODL PROXY - get - " + urlODL)
            else:
                response.status = 403
                strTables = ','.join(str(e) for e in tables)
                msg = "ODL Proxy - GET - Forbidden can not view " + jsonCheckUrl["target"] + " on table: " + str(
                    tableId) + " you can only access tables " + strTables
                logger.error(msg)
                return json.dumps({"msg": msg})
        else:
            resp = requests.get(urlODL, headers=headers)
            logger.info("ODL PROXY - get - " + urlODL)

        response.status = resp.status_code
        return resp.text
    except Exception as e:
        logger.exception("ODL PROXY - get - /restconf/" + url + " - "+str(e) )
        response.status = 500

@put('/restconf/<url:path>')
def putRestConf(url):
    logger.info("ODL PROXY - PUT - /restconf/" + url)
    # check the headears parameter
    # TODO for headears
    try:
        token = request.headers.get('API-Token')  # Token is experiment id
        accept = request.headers.get('Accept')

        # check the headears parameter
        if not accept:
            accept = 'application/json'

        if not token:
            response.status = 400
            msg = "ODL Proxy - Bad Request! Header API-Token NOT FOUND"
            logger.error(msg)
            return json.dumps({"msg": msg})
        else:
            if token in _experiments.keys():
                tables = _experiments[token]["flow_tables"]
            else:
                response.status = 403
                msg = "ODL Proxy - Experiment not found!"
                logger.error(msg)
                return json.dumps({"msg": msg})

        # check the url
        jsonCheckUrl = check_url(url)
        urlODL = "http://" + os.environ['ODL_HOST'] + ":" + os.environ['ODL_PORT'] + "/restconf/" + url
        headers = {'Accept': accept,
                   "Authorization": utils.encodeAuthorization(os.environ['ODL_USER'], os.environ['ODL_PASS']),
                   "Content-Type": "application/json"
                   }  # request.headers
        # EXEC
        if jsonCheckUrl["target"] == "flow":
            #nodeId = jsonCheckUrl["regex"].group(1)
            tableId = int(jsonCheckUrl["regex"].group(2))
            #flowId = int(jsonCheckUrl["regex"].group(3))

            if tableId in tables:
                try:
                    # dataj = json.loads(json.dumps(request.body.read().decode("utf-8"),ensure_ascii=True))
                    dataj = json.loads(request.body.read().decode("utf-8"))

                    if 'flow-node-inventory:flow' in dataj:
                        flow_node = dataj['flow-node-inventory:flow']
                        for f_n in flow_node:
                            if f_n['table_id'] in tables:
                                if 'instructions' in f_n:
                                    flow_node_instructions = f_n['instructions']
                                    if 'instruction' in flow_node_instructions:
                                        instructions = flow_node_instructions['instruction']
                                        for instruction in instructions:

                                            #Check the attribute go-to-table
                                            if 'go-to-table' in instruction:
                                                goToTable = instruction['go-to-table']
                                                tableDestination = goToTable['table_id']
                                                if tableDestination in tables or tableDestination == 17:
                                                    logger.debug("ODL PROXY - PUT - /restconf/" + url  + " go-to-table in range of experiment")
                                                else:
                                                    response.status = 403
                                                    strTables = ','.join(str(e) for e in tables)
                                                    msg = "ODL Proxy - PUT Forbidden can not modify table: " + str(
                                                        tableDestination) + " you can only access tables " + strTables
                                                    logger.error(msg)
                                                    return json.dumps({"msg": msg})
                                            # Check the attribute output-node-connector
                                            elif 'apply-actions' in instruction:
                                                applyActions = instruction['apply-actions']
                                                if 'action' in applyActions:
                                                    actions = applyActions['action']
                                                    for action in actions :
                                                        if 'output-action' in action:
                                                            outputAction = action['output-action']
                                                            if 'output-node-connector' in outputAction:
                                                                if outputAction['output-node-connector'].lower() == "table" or outputAction['output-node-connector'].lower() == "inport" or outputAction['output-node-connector'].lower() == "in-port" :
                                                                    logger.debug("ODL PROXY - PUT - /restconf/" + url + " output-node-connector " + outputAction['output-node-connector'] + " is allowed")
                                                                else:
                                                                    response.status = 403
                                                                    msg = "ODL Proxy - PUT -Forbidden can not use tag output-node-connector with value : " + outputAction['output-node-connector']
                                                                    logger.error(msg)
                                                                    return json.dumps({"msg": msg})


                            else:
                                response.status = 403
                                strTables = ','.join(str(e) for e in tables)
                                msg = "ODL Proxy - PUT- Forbidden can not modify table: " + str(
                                    f_n['table_id']) + " you can only access tables " + strTables
                                logger.error(msg)
                                return json.dumps({"msg": msg})

                except Exception as e:
                    response.status = 400
                    msg = "ODL Proxy - PUT - Bad Request! " + str(e)
                    logger.exception(msg)
                    return json.dumps({"msg": msg})

                    # print "code:" + str(dataj)
                dataj = json.dumps(dataj, ensure_ascii=False)
                resp = requests.put(urlODL, data=dataj, headers=headers)
                logger.info("ODL PROXY - /restconf/" + url + " - " + str(resp.status_code) + " PUT ")

                #logger.info("ODL PROXY - /restconf/" + url + " resp.status_code " + str(resp.status_code))
                logger.debug("ODL PROXY - /restconf/" + url + " resp.headers " + str(resp.headers))
                logger.debug("ODL PROXY - /restconf/" + url + " resp.text " + str(resp.text))
                # logger.debug("ODL PROXY - /restconf/" + url + " resp.content " + str(resp.content))

                response.status = resp.status_code

                return resp.text

            else:
                response.status = 403
                strTables = ','.join(str(e) for e in tables)
                msg = "ODL Proxy - PUT - Forbidden can not modify flow on table: " + str(
                    tableId) + " you can only access tables " + strTables
                logger.error(msg)
                return json.dumps({"msg": msg})

        elif jsonCheckUrl["target"] == "table" or jsonCheckUrl["target"] == "nodes" or jsonCheckUrl["target"] == "node":
            response.status = 403
            msg = "ODL Proxy - PUT - Forbidden can not modify " + jsonCheckUrl["target"]
            logger.error(msg)
            return json.dumps({"msg": msg})

        else:
            response.status = 404
            msg = "ODL Proxy - PUT -Resource Not Found!"
            logger.error(msg)
            return json.dumps({"msg": msg})

    except Exception as e:
        logger.exception("ODL PROXY - PUT - /restconf/" + url + " - " + str(e))
        response.status = 500

#@get('/restconf/<url:path>')
#@put('/restconf/<url:path>')
#@delete('/restconf/<url:path>')
"""
def do_proxy_jsonrpc(url):
    logger.debug("ODL PROXY - /restconf/" + url)

    # TODO for headears
    token = request.headers.get('API-Token')  # Token is experiment id
    accept = request.headers.get('Accept')

    # check the headears parameter
    if not accept:
        accept = 'application/json'

    if not token:
        response.status = 400
        msg = "ODL Proxy - Bad Request! Header API-Token NOT FOUND"
        return json.dumps({"msg": msg})
    else:
        if token in _experiments.keys():
            tables = _experiments[token]["flow_tables"]
        else:
            response.status = 403
            msg = "ODL Proxy - Experiment not found!"
            return json.dumps({"msg": msg})

    # check the url

    jsonCheckUrl =  check_url(url)
    urlODL = "http://" + os.environ['ODL_HOST'] + ":" + os.environ['ODL_PORT'] + "/restconf/" + url


    #flowregex = 'config/opendaylight-inventory:nodes/node/openflow:([0-9]*)/table/([0-9]*)/flow/([0-9]*)'
    #flow_search = re.search(flowregex, url, re.IGNORECASE)

    #tableregex = 'config/opendaylight-inventory:nodes/node/openflow:([0-9]*)/table/([0-9]*)'
    #table_search = re.search(tableregex, url, re.IGNORECASE)

    #nodesregex = 'config/opendaylight-inventory:nodes'
    #node_search = re.search(nodesregex, url, re.IGNORECASE)

    if jsonCheckUrl["target"] == "flow":
        nodeId = jsonCheckUrl["regex"].group(1)
        tableId = int(jsonCheckUrl["regex"].group(2))
        flowId = int(jsonCheckUrl["regex"].group(3))

        if tableId in tables:
            headers = {'Accept' : accept,
                       "Authorization": _authorization,
                       "Content-Type": "application/json"
                       } #request.headers

            if request.method == "GET":
                resp = requests.get(urlODL, headers=headers)
            elif request.method == "PUT":
                try:

                    #dataj = json.loads(json.dumps(request.body.read().decode("utf-8"),ensure_ascii=True))

                    dataj = json.loads(request.body.read().decode("utf-8"))
                    if 'flow-node-inventory:flow' in dataj:
                        flow_node = dataj['flow-node-inventory:flow']
                        for f_n in flow_node:
                            if f_n['table_id'] in tables:
                                 if 'instructions' in f_n:
                                     flow_node_instructions = f_n['instructions']
                                     if 'instruction' in flow_node_instructions:
                                        instructions = flow_node_instructions['instruction']
                                        for instruction in instructions:
                                            if 'go-to-table' in instruction:
                                                goToTable = instruction['go-to-table']
                                                tableDestination = goToTable['table_id']
                                                if tableDestination in tables or tableDestination == 17 :
                                                    print("go-to-table in range of experiment")
                                                else:
                                                    response.status = 403
                                                    strTables = ','.join(str(e) for e in tables)
                                                    msg = "ODL Proxy - Forbidden can not modify table: " + str(
                                                        tableDestination) + " you can only access tables " + strTables
                                                    return json.dumps({"msg": msg})

                            else:
                                response.status = 403
                                strTables = ','.join(str(e) for e in tables)
                                msg = "ODL Proxy - Forbidden can not modify table: " + str(
                                    f_n['table_id']) + " you can only access tables " + strTables
                                return json.dumps({"msg": msg})
									
                except Exception as e:
                    response.status = 400
                    msg = "ODL Proxy - Bad Request! " + str(e)
                    return json.dumps({"msg": msg})

                    # print "code:" + str(dataj)
                dataj = json.dumps(dataj, ensure_ascii=False)
                resp = requests.put(urlODL, data=dataj, headers=headers)

            logger.debug("ODL PROXY - /restconf/" + url + " resp.status_code " +  str(resp.status_code))
            logger.debug("ODL PROXY - /restconf/" + url + " resp.headers " + str(resp.headers))
            logger.debug("ODL PROXY - /restconf/" + url + " resp.text " + str(resp.text))
            #logger.debug("ODL PROXY - /restconf/" + url + " resp.content " + str(resp.content))

            response.status = resp.status_code
            return resp.text

        else:
            response.status = 403
            strTables = ','.join(str(e) for e in tables)
            msg = "ODL Proxy - Forbidden can not modify table: " + str(tableId) + " you can only access tables " + strTables
            return json.dumps({"msg": msg})

    elif jsonCheckUrl["target"] == "nodes":
        headers = {'Accept': accept,
                   "Authorization": _authorization
                   }  # request.headers
        resp = requests.get(urlODL, headers=headers)
        logger.debug("ODL PROXY - /restconf/" + url + " resp.status_code " + str(resp.status_code))
        logger.debug("ODL PROXY - /restconf/" + url + " resp.headers " + str(resp.headers))
        logger.debug("ODL PROXY - /restconf/" + url + " resp.text " + str(resp.text))

        response.status = resp.status_code
        return resp.json()

    else:
        response.status = 404
        msg = "ODL Proxy - Resource Not Found!"
        return json.dumps({"msg": msg})
 """

def start():
    #global _mySdnFilter
    #_experiments["test01"] = {"tenant": "123invalid456", "flow_tables": 300}
    logger.info("starting up 0.0.0.0:8001")
    #_mySdnFilter = WhitelistFilter(["help", "list.methods"])
    bottle.run(host='0.0.0.0', port=8001)

