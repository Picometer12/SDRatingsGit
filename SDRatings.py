import math
import os
from collections import namedtuple
from copy import copy
import random

import modules.scripts as scripts
import gradio as gr

from modules import images
from modules.processing import process_images, Processed
from modules.shared import opts, cmd_opts, state
import modules.sd_samplers

keywordList = []

state = "noComparison" #can be noComparison, ready, rated, errorGenerating

oldInputs = ["", ""] #used to see if settings have changed

eloScale = 32 #used in elo algorithm. This is the max change in elo rating. 
useNewcomerEloMultiplier = True



#used in displaying the images that need to be rated, separate from generation image area
#imagesToRate = [] #move this into contest?

contestantList = []
contestList = []

#Allows fetching of single images
singleImageQueue = []
singleImageIndex = -1
firstPushSinceEmpty = True; #set to true whenever the singleImageQueue is empty so that the next button push doesn't delete the single images in queue

class Tag():
    def __init__(self, tagString):
        self.tagString = tagString
        self.tagName = "undefined"
        self.rating = 1500
        self.timesRated = 0

    # Overall:1556:1, but second or third element could be missing
    def unpack(self):
        tagStringList = self.tagString.split(":")
        self.tagName = tagStringList[0]

        if len(tagStringList) > 1:
            self.rating = int(tagStringList[1])

        if len(tagStringList) > 2:
            self.timesRated = int(tagStringList[2])

class Contestant():
    def __init__(self, dataString):
        self.dataString = dataString.strip()
        self.keyword = "notDefined"
        self.tags = []
    
    #copied from getElo. Can probably make getElo obsolete after refactor
    #string in format: Anton Fadeev(Overall:1556:1, ConceptArtist:1500)
    def unpack(self):
        self.keyword = self.dataString.split("(")[0]
        
        tagsString = self.dataString.split("(")[1]  #Overall:1556:1, ConceptArtist:1500)
        tagsString = tagsString[:-1]                   #Overall:1556:1, ConceptArtist:1500
        tagStringList = tagsString.split(",")

        for tag in tagStringList:
            self.tags.append(Tag(tag))
            self.tags[-1].unpack()

        #groupString = line.split("(")[1]
        #groupList = groupString.split(",")
                        
        #data is in the form groupName:1500 or groupName:1500:2
        #for grp in groupList:
        #    if group in grp:
        #        return grp.split(":",1)[1]
    


    def repack(self):
        newString = ""
        newString += self.keyword + "("
        for tag in self.tags:
            newString += tag.tagName + ":"
            newString += tag.rating + ":"
            newString += tag.timesRated + ")"
        return newString
            

#Generation and voting will not occur together. Pack all information that we need to vote into each Contest.
class Contest():
    def __init__(self, keywords, contestGroups, grid, filename):
        self.keywords = keywords
        self.contestGroups = contestGroups
        self.grid = grid
        self.filename = filename


def draw_xy_grid(xs, ys, x_label, y_label, cell):
    # I may have messed this up in a way that's not bothering me righ now
    # Probably copied from wildcards or xymatrix, figure out where this come from if it ever needs to be repaired
    res = []

    ver_texts = [[images.GridAnnotation(y_label(y))] for y in ys]
    #ver_texts = ["", "", ""]
    hor_texts = [[images.GridAnnotation(x_label(x))] for x in xs]

    first_processed = None

    state.job_count = len(xs) * len(ys)

    for iy, y in enumerate(ys):
        for ix, x in enumerate(xs):
            state.job = f"{ix + iy * len(xs) + 1} out of {len(xs) * len(ys)}"

            processed = cell(x, y)
            if first_processed is None:
                first_processed = processed

            res.append(processed.images[0])

    grid = images.image_grid(res, rows=len(ys))
    grid = images.draw_grid_annotations(grid, res[0].width, res[0].height, hor_texts, ver_texts)
    

    first_processed.images = [grid]

    return first_processed


#Gradio doesnt like it when I pass strings using button click inputs, so we're doing it this way
def voteLeft():
    global state, contestList

    #Todo make the error messages readable within gradio
    if state == "ready":
        results = ratingAdjust("left")
        state = "rated"
        #contestList.pop(0)
        return results
    elif state == "noComparison":
        raise gr.Error("Nothing to rate, generate images first")
    elif state == "rated":
        raise gr.Error("Already rated or couldn't decide, generate new images first.")
    else:
        raise gr.Error("Bad Developer. Variable state should only take values of noComparison, ready, or rated")

def voteRight():
    global state, contestList
    
    if state == "ready":
        results = ratingAdjust("right")
        state = "rated"
        #contestList.pop(0)
        return results
    elif state == "noComparison":
        raise gr.Error("Nothing to rate, generate images first")
    elif state == "rated":
        raise gr.Error("Already rated or couldn't decide, generate new images first.")
    else:
        raise gr.Error("Bad Developer. Variable state should only take values of noComparison, ready, or rated")

def doOver():
    global state, contestList

    if state == "ready":
        state = "rated"
        leftMessage = contestList[0].keywords[0] + " draws. "
        rightMessage = contestList[0].keywords[1] + " draws. "
        
        for group in contestList[0].contestGroups:
            #leftMessage += f"{group}: {getElo(contestList[0].keywords[0], group).split(":")[0] } , "
            leftMessage += group + ": " + getElo(contestList[0].keywords[0], group, contestList[0].filename).split(":")[0] +", "
            rightMessage += group + ": " + getElo(contestList[0].keywords[1], group, contestList[0].filename).split(":")[0] +", "

        #contestList.pop(0)
        return [leftMessage, rightMessage]
        
    elif state == "noComparison":
        raise gr.Error("Nothing to rate, generate images first")
    elif state == "rated":
        raise gr.Error("Already rated or couldn't decide, generate new images first.")
    else:
        raise gr.Error("Bad Developer. Variable state should only take values of noComparison, ready, or rated")
        
    #Todo: find a way to call on generate and send the outcome to the front? 
    #For now just skip without rating


def getImageforUI():
    global state, singleImageIndex, firstPushSinceEmpty
    if len(contestList) > 0:
        state = "ready"

        if not firstPushSinceEmpty:
            contestList.pop(0)
            del singleImageQueue[:6]
            if len(singleImageQueue) == 0:
                firstPushSinceEmpty = True
        else:
            firstPushSinceEmpty = False
        singleImageIndex = -1
        return contestList[0].grid
    else:
        raise gr.Error("No images in queue. Try generating images or maybe something has gone wrong.")
 
def cycleSingleImages():
    global singleImageIndex
    singleImageIndex += 1

    if singleImageIndex == 6:
        singleImageIndex = -1
        return contestList[0].grid
    else:
        return singleImageQueue[singleImageIndex] 

def removeTagLeft(tag):
    RemoveTag(tag, contestList[0].keywords[0], contestList[0].filename)

def removeTagRight(tag):
    RemoveTag(tag, contestList[0].keywords[1], contestList[0].filename)

def RemoveTag(tag, keyword, filename):
    if tag != "":
        file_dir = os.path.dirname(os.path.realpath("__file__"))
        read_file = os.path.join(file_dir, f"scripts/SDRatings/{filename}.txt")    
        if os.path.exists(read_file):
            with open(read_file, 'r') as f:
                #I'm sure there's a better way to do this than opening and closing in different modes
                replacedContent = ""
                
                #lines are in format Anton Fadeev(Overall:1500, ConceptArtists:1500)
                for line in f.read().strip().splitlines():
                    #line = line.strip()

                    if keyword in line:
                        #remove the parentheses on the end
                        line = line[:-1]
                        #add the keyword back in 
                        replacedContent += line.split("(")[0] + "("

                        groupString = line.split("(")[1]
                        groupList = groupString.split(",")

                        #grp in form Overall:1500:1 if has been updated. Could be Overall:1500 in else
                        for grp in groupList:
                            if tag in grp:
                                #empty string
                                print(grp + " removed from " + keyword + ". Before:" + line )
                                replacedContent += ""

                            else:
                                replacedContent += grp + ","

                        #remove the extra comma and add a ) and new line.
                        #if list there are no tags left, there will not be a comma, so check for comma
                        if (replacedContent[-1] == ','):
                            replacedContent = replacedContent[:-1]
                        replacedContent += ")\n"

                        
                    else:
                        replacedContent += line + "\n"
                            
                f.close()
                replacedContent.strip()
                    
            with open(read_file, 'w') as f:
                f.writelines(replacedContent)
                f.close()
    else:
        raise gr.Error("Empty string. Type a tag in field: Name of tag to be removed")




    #Moved from ratingAdjust -- shouldn't be a problem?
#could do all groups at once, but I've already written this for one so let's just call it multiple times
def getElo(keyword, group, filename):
    file_dir = os.path.dirname(os.path.realpath("__file__"))
    read_file = os.path.join(file_dir, f"scripts/SDRatings/{filename}.txt")    
    if os.path.exists(read_file):
        with open(read_file, 'r') as f:
                
            #if a line contains group, return keyword from format keyword(group1:1500, group2:1500,...)
            #if two colons between commas, second number is number of ratings. keyword(group1:1500:2)
            for line in f.read().strip().splitlines():  
                #remove the ending parentheses
                line = line[:-1]
                if keyword in line:
                    groupString = line.split("(")[1]
                    groupList = groupString.split(",")
                        
                    #data is in the form groupName:1500 or groupName:1500:2
                    for grp in groupList:
                        if group in grp:
                            return grp.split(":",1)[1]

            f.close()
    #if we get to this point, there's a problem
    raise gr.Error("getEloNew didnt find the group within the keyword")
    return 0

def ratingAdjust(txtWinner):
    print(txtWinner + " wins")

    


    #Todo: If this is slow, try to save something in the getElo method that will help us SetElo faster
    #I'm guessing this sort of thing is not slow on this scale

    def setElo(keyword, group, newElo, timesRated, filename):
        file_dir = os.path.dirname(os.path.realpath("__file__"))
        read_file = os.path.join(file_dir, f"scripts/SDRatings/{filename}.txt")    
        if os.path.exists(read_file):
            with open(read_file, 'r') as f:
                
                #I'm sure there's a better way to do this than opening and closing in different modes
                replacedContent = ""
                
                #lines are in format Anton Fadeev(Overall:1500, ConceptArtists:1500)
                for line in f.read().strip().splitlines():
                    #line = line.strip()

                    if keyword in line:
                        #remove the parentheses on the end
                        line = line[:-1]
                        #add the keyword back in 
                        replacedContent += line.split("(")[0] + "("

                        groupString = line.split("(")[1]
                        groupList = groupString.split(",")

                        #grp in form Overall:1500:1 if has been updated. Could be Overall:1500 in else
                        for grp in groupList:
                            if group in grp:
                                #add in the keyword then the new rating
                                replacedContent += grp.split(":")[0] + ":" + str(newElo) + ":" + str(timesRated) + ","

                            else:
                                replacedContent += grp + ","

                        #remove the extra comma and add a ) and new line.
                        replacedContent = replacedContent[:-1] + ")\n" 
                    else:
                        replacedContent += line + "\n"
                            
                f.close()
                replacedContent.strip()
                    
            with open(read_file, 'w') as f:
                f.writelines(replacedContent)
                f.close()

    eloRatingChunks1 = []
    eloRatingChunks2 = []
    originalElos1 = []
    originalElos2 = []
    timesRated1 = []
    timesRated2 = []
    expectedLeftWinProb = []
    newElos1 = []
    newElos2 = []
    eloMultipliers1 = []
    eloMultipliers2 = []

    differenceParam = 400 #elo guide recommends 400. Figure out an intuitive explanation for this constant

    leftResult = ""
    rightResult = ""

    if txtWinner == "left":
        winLeftBinary = 1
        #print(contestList[0].keywords[0] + " wins")
        leftResult += f"{contestList[0].keywords[0]} wins. "
        rightResult += f"{contestList[0].keywords[1]} loses. "
    elif txtWinner == "right":
        winLeftBinary = 0
        #print(contestList[0].keywords[1] + " wins")
        leftResult += f"{contestList[0].keywords[0]} loses: "
        rightResult += f"{contestList[0].keywords[1]} wins: "
    else:
        #Todo throw a proper error message into automatic1111
        print("txtWinner should be left or right")

    i = 0
    for group in contestList[0].contestGroups:
        #get elo returns in format "keyword" or "keyword:1"
        
        eloRatingChunks1.append(getElo(contestList[0].keywords[0], group, contestList[0].filename ).split(":"))
        eloRatingChunks2.append(getElo(contestList[0].keywords[1], group, contestList[0].filename).split(":"))

        originalElos1.append(int(eloRatingChunks1[i][0]))
        originalElos2.append(int(eloRatingChunks2[i][0]))

        #Todo: would be cleaner for chunks to be temporary instead of an array

        if len(eloRatingChunks1[i]) == 1:
            timesRated1.append(1)
        else:
            timesRated1.append(int(eloRatingChunks1[i][1]))

        if len(eloRatingChunks2[i]) == 1:
            timesRated2.append(1)
        else:
            timesRated2.append(int(eloRatingChunks2[i][1]))

        if useNewcomerEloMultiplier:
            eloMultipliers1.append(max(1,int (5.5 - 0.5*timesRated1[i])))
            eloMultipliers2.append(max(1,int (5.5 - 0.5*timesRated2[i])))

        expectedLeftWinProb.append( 1/(1 + pow(10, (originalElos2[i] - originalElos1[i])/differenceParam)))

        newElos1.append(round(originalElos1[i] + eloScale*eloMultipliers1[i]*(winLeftBinary - expectedLeftWinProb[i])))
        newElos2.append(round(originalElos2[i] - eloScale*eloMultipliers2[i]*(winLeftBinary - expectedLeftWinProb[i])))

        timesRated1[i] += 1
        timesRated2[i] += 1

        setElo(contestList[0].keywords[0], group, newElos1[i], timesRated1[i], contestList[0].filename)
        setElo(contestList[0].keywords[1], group, newElos2[i], timesRated2[i], contestList[0].filename)

        
        #print(contestList[0].keywords[0] + ":" + group + " changed from " + str(originalElos1[i]) + " to " + str(newElos1[i])) 
        #print(contestList[0].keywords[1] + ":" + group + " changed from " + str(originalElos2[i]) + " to " + str(newElos2[i]))

        leftResult += f"{group}: {str(originalElos1[i])} to {str(newElos1[i])} ({str(newElos1[i] - originalElos1[i])}), "
        rightResult += f"{group}: {str(originalElos2[i])} to {str(newElos2[i])} ({str(newElos2[i] - originalElos2[i])}), "
        

        i += 1
    return [leftResult, rightResult]
    
def exportKeywords(tagName, exportType, fileName):
    file_dir = os.path.dirname(os.path.realpath("__file__"))
    read_file = os.path.join(file_dir, f"scripts/SDRatings/{fileName}.txt")

    outputContestants = [];
    
    
    if os.path.exists(read_file):
        with open(read_file, 'r') as f:
            #if a line contains all specified groups, return keyword from format keyword(group1, group2,...)
            for line in f.read().splitlines():
                keep = True
                if tagName not in line:
                    keep = False
                        
                if keep:
                    tagStrings = []
                    #contestantList.append(Contestant(line))
                    thisContestant = Contestant(line)
                    thisContestant.unpack()

                    #move the first tag specified to the front for sorting purposes
                    tagIndex = 0
                    for i in range(len(thisContestant.tags)):
                        if thisContestant.tags[i].tagName == tagName:
                            tagIndex = i

                    thisContestant.tags.insert(0, thisContestant.tags.pop(tagIndex))      
                    outputContestants.append(thisContestant)
            f.close()
        
        outputContestants.sort(key=lambda x: x.tags[0].rating)
        outputContestants.reverse()
        #"Keyword only", "Keyword:Rating", "All Ratings"]

        file_dir = os.path.dirname(os.path.realpath("__file__"))
        write_file = os.path.join(file_dir, f"scripts/SDRatings/Output_{tagName}.txt")
        with open(write_file, 'w') as f:
            for contestant in outputContestants:
                firstTag = True
                f.write(f"{contestant.keyword}")

                if exportType == "All Ratings":
                    for t in contestant.tags:
                        if firstTag:
                            f.write("(")
                            firstTag = False
                        else:
                            f.write(",")
                        f.write(f"{t.tagName}:{t.rating}:{t.timesRated}")
                    f.write(")")
                    
                elif exportType == "Keyword:Rating":
                    f.write(f":{contestant.tags[0].rating}")
                f.write("\n")
            f.close()
    else:
        raise gr.Error("Couldn't read file -- check Name of txt file in SDRatings")





class Script(scripts.Script):
    def title(self):
        return "SDRatings"

    def ui(self, is_img2img):
        
        gr.Markdown(" Vote for the left or right keyword after image generation") #add some vertical white space
        with gr.Row():
            fetch_image_button = gr.Button(value = "Cycle images")
            left_wins = gr.Button(value = "Vote Left")
            cant_decide = gr.Button(value = "Can't Decide")
            right_wins = gr.Button(value = "Vote Right")
            next_image = gr.Button(value = "Next Image in Queue")
            

        gr.Markdown(" <br/> ") 

        with gr.Row():
            leftResultsTextUI = gr.Textbox(label="Left Result ", value = "")
            rightResultsTextUI = gr.Textbox(label="Right Result ", value = "")
            
            

        ratingImageUI = gr.Image()

        left_wins.click(voteLeft, outputs = [leftResultsTextUI, rightResultsTextUI])
        cant_decide.click(doOver, outputs = [leftResultsTextUI, rightResultsTextUI])
        right_wins.click(voteRight, outputs = [leftResultsTextUI, rightResultsTextUI])
        next_image.click(fn = getImageforUI, outputs = ratingImageUI )
        fetch_image_button.click(fn = cycleSingleImages, outputs = ratingImageUI)

        gr.Markdown(" <br/> ") #add some vertical white space
        
        gr.Markdown("Fill this out before image generation. ") #add some vertical white space
        gr.Markdown(" <br/> ") 
        
        with gr.Row(): 
            #Todo: resetQueueCheckbox is a temporary solution. Create a better, more intuitive flow for resetting the queue, especially when changing modes. 
            resetQueueCheckbox = gr.Checkbox(label = "Reset Queues", value = True)
            fileNameTextbox = gr.Textbox(label="Name of txt file in SDRatings, exclude .txt ", value = "SDRatings")
            keywordGroups = gr.Textbox(label="Rated Groups - each of these tags will be rated ", value = "Overall")
            unratedGroups = gr.Textbox(label="Unrated Groups - used as filter but will not be rated ", value = "")

        with gr.Row():
            modeDropdown = gr.Dropdown(label = "Comparison Mode", choices = ["Similar", "Random", "Quickrate"], value = "Similar")
            similarMethodDropdown = gr.Dropdown(label = "Similar Algorithm", choices = ["Random", "High to Low", "Low to High", "Lowest Times Rated"], value = "Random")
            keywordForQuickRate = gr.Textbox(label="Keyword for Quickrate")

        

        
        gr.Markdown("(Not functional yet.) Remove an unwanted tag here. Use between voting and Next Image.  ")
        gr.Markdown(" <br/> ") 

        #Todo: Not functioning yet
        with gr.Row():
            removeTagInput = gr.Textbox(label="Name of tag to be removed")
            removeTagLeftButton = gr.Button(value = "Remove from left keyword")
            removeTagRightButton = gr.Button(value = "Remove from right keyword")

        removeTagLeftButton.click(removeTagLeft, inputs = [removeTagInput])
        removeTagRightButton.click(removeTagRight, inputs = [removeTagInput])

        gr.Markdown("Miscellaneous Settings ") #add some vertical white space
        gr.Markdown(" <br/> ") 

        number_of_comparisons = gr.Textbox(label="Number of Images per keyword (integer)", value = 3)
        eloScaleInput = gr.Slider(label = "Max elo change. Matching ratings will change by half this amount.", minimum = 16, maximum = 100, value = 32, step = 1)
        
        
        useNewcomerEloMultiplierInput = gr.Checkbox(label = "Boost elo change for new tags.", value = True)
        displayGrids = gr.Checkbox(label = "Display Grids in generation output (slows down conclusion for large batch count)", value = False)
        allowListeners = gr.Checkbox(label = "Allow listeners to modify prompt ", value = True)
        enableImageFetch = gr.Checkbox(label = "Enable single image fetcher", value = True)

        with gr.Row(): 
            exportTag = gr.Textbox(label="Export txt file of keywords sorted by this tag")
            exportType = gr.Dropdown(label = "Export includes...", choices = ["Keyword only", "Keyword:Rating", "All Ratings"], value = "Keyword only")
            exportButton = gr.Button(value = "Export txt")

        exportButton.click(exportKeywords, inputs = [exportTag, exportType, fileNameTextbox])
            
            


    
        #different_seeds = gr.Checkbox(label='Use different seed for each picture', value=False)

        return [ number_of_comparisons, keywordGroups, unratedGroups, eloScaleInput, useNewcomerEloMultiplierInput, displayGrids, modeDropdown, similarMethodDropdown, enableImageFetch, keywordForQuickRate, resetQueueCheckbox, fileNameTextbox, allowListeners ]

    def run(self, p, number_of_comparisons, keywordGroups, unratedGroups, eloScaleInput, useNewcomerEloMultiplierInput, displayGrids, modeDropdown, similarMethodDropdown, enableImageFetch, keywordForQuickRate, resetQueueCheckbox, fileNameTextbox, allowListeners):
        modules.processing.fix_seed(p)

        global state, eloScale, useNewcomerEloMultiplier

        groups = keywordGroups.split(",")
        unratedGroupList = unratedGroups.split(",")
        eloScale = int(eloScaleInput)
        useNewcomerEloMultiplier = useNewcomerEloMultiplierInput
        listeners = [] #put Listener objects in here

        print ( keywordForQuickRate)


        for i in range(len(groups)):
            groups[i] = groups[i].strip()


        for i in range(len(unratedGroupList)):
            unratedGroupList[i] = unratedGroupList[i].strip()
        
        def replace_wildcard(chunk):
            if " " not in chunk:
                file_dir = os.path.dirname(os.path.realpath("__file__"))
                replacement_file = os.path.join(file_dir, f"scripts/wildcards/{chunk}.txt")
                if os.path.exists(replacement_file):
                    with open(replacement_file, encoding="utf8") as f:
                        return random.choice(f.read().splitlines())
            return chunk

        #probably should refactor and just use Contestant List, but let's make sure this works first
        def populateKeywordList():
            for contestant in contestantList:
                #print(contestant.keyword + " added to keywordList")
                keywordList.append(contestant.keyword)
        
        class Listener():
            def __init__(self, name, posPrompt, negPrompt):
                self.name = name
                self.posPrompt = posPrompt
                self.negPrompt = negPrompt

        def populateListeners():
            file_dir = os.path.dirname(os.path.realpath("__file__"))
            read_file = os.path.join(file_dir, f"scripts/listeners/listeners.txt")
            
            if os.path.exists(read_file):
                with open(read_file, 'r') as f:
                    #if a line contains all specified groups, return keyword from format keyword(group1, group2,...)
                    for line in f.read().splitlines():
                        #remove the { and } on the ends
                        line = line.strip()
                        line = line[1:-1]

                        # format is: {input1,input2,input3}{positive}{negative}
                        names = line.split("}{")[0]
                        positiveAddString = line.split("}{")[1]
                        negativeAddString = line.split("}{")[2]

                        for name in names.split(","):
                            name = name.strip()
                            listeners.append(Listener(name,positiveAddString,negativeAddString))                      


        def populateContestantList():
            #keyword = []
            global contestantList
            quickContestant = Contestant("default")

            file_dir = os.path.dirname(os.path.realpath("__file__"))
            read_file = os.path.join(file_dir, f"scripts/SDRatings/{fileNameTextbox}.txt")
            
            if os.path.exists(read_file):
                with open(read_file, 'r') as f:
                    #if a line contains all specified groups, return keyword from format keyword(group1, group2,...)
                    for line in f.read().splitlines():
                        keep = True
                        for group in groups + unratedGroupList:
                            if group not in line:
                                keep = False
                        
                        if keep:
                            tagStrings = []
                            #contestantList.append(Contestant(line))
                            thisContestant = Contestant(line)
                            thisContestant.unpack()
 

                            #move the first tag specified to the front for sorting purposes
                            tagIndex = 0
                            for i in range(len(thisContestant.tags)):
                                if thisContestant.tags[i].tagName == groups[0]:
                                    tagIndex = i

                            thisContestant.tags.insert(0, thisContestant.tags.pop(tagIndex))
                            
                            contestantList.append(thisContestant)

                            if thisContestant.keyword == keywordForQuickRate.strip():
                                print("QuickRate Match " + thisContestant.keyword)
                                quickContestant = thisContestant


                #similarMethodDropdown = gr.Dropdown(label = "Similar Algorithm", choices = ["Random", "High to Low", "Low to High", "Lowest Times Rated"], value = "Random")
                if modeDropdown == "Similar":
                    #sorted low to high
                    contestantList.sort(key=lambda x: x.tags[0].rating)

                    if similarMethodDropdown == "High to Low":
                        contestantList.reverse()
                    elif similarMethodDropdown == "Random":
                        #make even by duplicating one contestant

                        #Todo: I got a duplicate. How? (keyword vs same keyword)
                        if len(contestantList) % 2 == 1:
                            contestantList.append(contestantList[-2])
                        
                        #pick a random number from 0 to length - 1. Grab i and i+1. Now pick  a random number from 2 to length - 1...
                        lastIndex = len(contestantList) - 2 
                        for i in range(0, len(contestantList)-2, 2):
                            randomIndex = random.randrange(i, lastIndex, 2)
                            contestantList.insert(i,contestantList.pop(randomIndex))
                            contestantList.insert(i + 1,contestantList.pop(randomIndex + 1))
                    elif similarMethodDropdown == "Lowest Times unratedGroupList Rated":
                        doNothing = "okay" #there's work to do
                    else: #sorted low to high already, don't do anything
                        doNothing = "okay" #already handled

                elif modeDropdown == "Random":          
                    random.shuffle(contestantList)
                else: # modeDropdown == "Quickrate":
                    newList = []
                    random.shuffle(contestantList)
                    for i in range (0, len(contestantList)):
                        if contestantList[i].keyword != quickContestant.keyword:
                            if random.randint(0, 1) == 0:
                                newList.append(contestantList[i])
                                newList.append(quickContestant)
                            else:
                                newList.append(quickContestant)
                                newList.append(contestantList[i])

                    contestantList = newList




                    #Todo: algorithm for lowest times rated can be: after sorting by elo (1) determine lowest (make a list of unique counts so you can skip if needed) 
                    #(2) seek the lowest and grab them and the neighbor, repeat for full length of list. Then repeat fo
                    '''
                    if startingPointDropdown == "Random":
                        #pick a random place to cut the List
                    else: #startingPointDropdown == "Lowest TimesRated
                    '''
            #Reminders:                     
            #modeDropdown = gr.Dropdown(label = "Comparison Mode", choices = ["Similar", "Random"], value = "Similar")
            #startingPointDropdown = gr.Dropdown(label = "Starting Point", choices = ["Random", "Lowest Times Rated"], value = "Random")


        #Don't know why I was having issues with Number instead of textbox, my workaround
        number_of_comparisons = int(number_of_comparisons)

        #global keyword1, keyword2, keywordList
        global keywordList, oldInputs, contestantList, contestants
        
        #determine if settings have changed, record these settings to compare next time
        if oldInputs[0] == keywordGroups and oldInputs[1] == unratedGroups:
            newSettings = False
        else:
            newSettings = True

        oldInputs = [keywordGroups, unratedGroups]

        #Todo: Change logic and move into the for loop so that you can loop around if batch count is high
        #Todo: do something here if you ever use batch size
        #Todo: there something wrong between this logic and the called on functions causing images to sometimes be compared to themselves.
        if len(keywordList) < 2 * p.n_iter or newSettings or resetQueueCheckbox:
            contestantList = []
            keywordList = []
            
            populateContestantList()
            populateKeywordList()
            if len(keywordList) < 2:               
                #keyword1 = "defaulta"
                #keyword2 = "defaultb"
                raise gr.Error("There aren't two or more keywords with the group")

        original_prompt = p.prompt[0] if type(p.prompt) == list else p.prompt
        original_negative_prompt = p.negative_prompt[0] if type(p.negative_prompt) == list else p.negative_prompt

        #add keyword at the start of prompt if not present already
        if ("keyword" not in original_prompt and "keyword" not in original_negative_prompt):
            original_prompt = "keyword " + original_prompt
        
        #insert extra words into prompts based on listeners.txt
        populateListeners()
        if allowListeners:
            for listener in listeners:
                if (listener.name in original_prompt):
                    original_prompt = listener.posPrompt + original_prompt
                    original_negative_prompt = listener.negPrompt + original_negative_prompt


        #Todo: figure out what to do with batch size if anything
        

        wildcard_prompts = ["".join(replace_wildcard(chunk) for chunk in original_prompt.split("__")) for _ in range(p.n_iter * number_of_comparisons)]
        wildcard_negative_prompts = ["".join(replace_wildcard(chunk) for chunk in original_negative_prompt.split("__")) for _ in range(p.n_iter * number_of_comparisons)]

        #Handle cascading wildcards
        doWildcard = True
        wildcardDebugCounter = 0

        while doWildcard and wildcardDebugCounter < 51:
            wildcardDebugCounter += 1

            if wildcardDebugCounter == 50:
                raise gr.Error("Hit 50 loops. Do you have a neverending cascading wildcard?")


            doWildcard = False
            for i in range(0, len(wildcard_prompts)):
                wildcard_prompts[i] = "".join(replace_wildcard(chunk) for chunk in wildcard_prompts[i].split("__"))
                wildcard_negative_prompts[i] = "".join(replace_wildcard(chunk) for chunk in wildcard_negative_prompts[i].split("__"))
                if "__" in wildcard_prompts[i] or "__" in wildcard_negative_prompts[i]:
                    doWildCard = True
                
        all_prompts = []
        all_negative_prompts = []

        for i in range(len(wildcard_prompts)):
            all_prompts.append(wildcard_prompts[i].replace("keyword", keywordList[2 * (i // number_of_comparisons)]))
            all_prompts.append(wildcard_prompts[i].replace("keyword", keywordList[2 * (i // number_of_comparisons) + 1]))
            all_negative_prompts.append(wildcard_negative_prompts[i].replace("keyword", keywordList[2 * (i // number_of_comparisons)]))
            all_negative_prompts.append(wildcard_negative_prompts[i].replace("keyword", keywordList[2 * (i // number_of_comparisons) + 1]))
        
        #Todo: do something if data is not valid

        p.n_iter = math.ceil(len(all_prompts) / p.batch_size)
        p.do_not_save_grid = True

        print("all_prompts length : " + str(len(all_prompts)))
        p.prompt = all_prompts
        p.negative_prompt = all_negative_prompts
        p.seed = [p.seed + (i / 2) for i in range(len(all_prompts))]
        p.prompt_for_display = original_prompt
        processed = process_images(p)
        
        if (enableImageFetch):
            global singleImageQueue
            for image in processed.images:
                singleImageQueue.append(image)

        global contestList

        # grid = images.image_grid(processed.images, p.batch_size, rows=1 << ((len(prompt_matrix_parts) - 1) // 2))
        # grid = images.draw_prompt_matrix(grid, p.width, p.height, prompt_matrix_parts)
        #print ("Length of all_prompts" + strlen(all_prompts))
        
        for i in range(len(all_prompts) // 2 // number_of_comparisons):
            if displayGrids:
                gridBuffer = i
            else:
                gridBuffer = 0
            
            grid = images.image_grid(processed.images[i * 6 + gridBuffer : i * 6 + 6 + gridBuffer ], p.batch_size, rows=number_of_comparisons)
            
            if displayGrids:
                processed.images.insert(i, grid) #Package all info into to be voted on later
                processed.infotexts.insert(i, processed.infotexts[6*i + i ]) 

            #To do: put in "(vs keywordList[1]) or something like that in the info text?
            contestList.append(Contest(keywordList[0:2], groups, grid, fileNameTextbox))
            keywordList.pop(0)
            keywordList.pop(0)

        if displayGrids:
            processed.index_of_first_image = i
        else:
            processed.index_of_first_image = 0

        #Todo get labels to behave -- or maybe not, so ratings are unbiased. Could add check box
        #grid = images.draw_prompt_matrix(grid, p.width, p.height, all_prompts)
        #grid = images.draw_prompt_matrix(grid, p.width, p.height, all_prompts[0:2])

        #Todo add checks to make sure an image propertly displayed

        state = "ready" #allows rating buttons to work

        if opts.grid_save:
            images.save_image(processed.images[0], p.outpath_grids, "prompt_matrix", extension=opts.grid_format, prompt=original_prompt, seed=processed.seed, grid=True, p=p)

        return processed
