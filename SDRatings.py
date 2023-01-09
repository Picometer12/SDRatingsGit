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
contestList = []

#Generation and voting will not occur together. Pack all information that we need to vote into each Contest.
class Contest():
    def __init__(self, keywords, contestGroups, grid):
        self.keywords = keywords
        self.contestGroups = contestGroups
        self.grid = grid


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
        contestList.pop(0)
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
        contestList.pop(0)
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
        contestList.pop(0)
    elif state == "noComparison":
        raise gr.Error("Nothing to rate, generate images first")
    elif state == "rated":
        raise gr.Error("Already rated or couldn't decide, generate new images first.")
    else:
        raise gr.Error("Bad Developer. Variable state should only take values of noComparison, ready, or rated")
        
    #Todo: find a way to call on generate and send the outcome to the front? 
    #For now just skip without rating


def getImageforUI():
    global state
    if len(contestList) > 0:
        state = "ready"
        return contestList[0].grid
    else:
        raise gr.Error("No images in queue. Try generating images or maybe something has gone wrong.")
    

def ratingAdjust(txtWinner):
    print(txtWinner + " wins")

    #could do all groups at once, but I've already written this for one so let's just call it multiple times
    def getElo(keyword, group):
        file_dir = os.path.dirname(os.path.realpath("__file__"))
        read_file = os.path.join(file_dir, f"scripts/SDRatings/SDRatings.txt")    
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


    #Todo: If this is slow, try to save something in the getElo method that will help us SetElo faster
    #I'm guessing this sort of thing is not slow on this scale

    def setElo(keyword, group, newElo, timesRated):
        file_dir = os.path.dirname(os.path.realpath("__file__"))
        read_file = os.path.join(file_dir, f"scripts/SDRatings/SDRatings.txt")    
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
        
        eloRatingChunks1.append(getElo(contestList[0].keywords[0], group).split(":"))
        eloRatingChunks2.append(getElo(contestList[0].keywords[1], group).split(":"))

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
            eloMultipliers2.append(max(1,int (5.5 - 0.5*timesRated1[i])))

        expectedLeftWinProb.append( 1/(1 + pow(10, (originalElos2[i] - originalElos1[i])/differenceParam)))

        newElos1.append(round(originalElos1[i] + eloScale*eloMultipliers1[i]*(winLeftBinary - expectedLeftWinProb[i])))
        newElos2.append(round(originalElos2[i] - eloScale*eloMultipliers1[i]*(winLeftBinary - expectedLeftWinProb[i])))

        timesRated1[i] += 1
        timesRated2[i] += 1

        setElo(contestList[0].keywords[0], group, newElos1[i], timesRated1[i])
        setElo(contestList[0].keywords[1], group, newElos2[i], timesRated2[i])

        
        print(contestList[0].keywords[0] + ":" + group + " changed from " + str(originalElos1[i]) + " to " + str(newElos1[i])) 
        print(contestList[0].keywords[1] + ":" + group + " changed from " + str(originalElos2[i]) + " to " + str(newElos2[i]))

        leftResult += f"{group}: {str(originalElos1[i])} to {str(newElos1[i])} ({str(newElos1[i] - originalElos1[i])}), "
        rightResult += f"{group}: {str(originalElos2[i])} to {str(newElos2[i])} ({str(newElos2[i] - originalElos2[i])}), "
        

        i += 1
    return [leftResult, rightResult]
    

class Script(scripts.Script):
    def title(self):
        return "SDRatings"

    def ui(self, is_img2img):
        
        gr.Markdown(" Vote for the left or right keyword after image generation") #add some vertical white space
        with gr.Row():
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
        cant_decide.click(doOver)
        right_wins.click(voteRight, outputs = [leftResultsTextUI, rightResultsTextUI])
        next_image.click(fn = getImageforUI, outputs = ratingImageUI )

        gr.Markdown(" <br/> ") #add some vertical white space
        
        gr.Markdown("Fill this out before image generation. ") #add some vertical white space
        gr.Markdown(" <br/> ") 
        
        with gr.Row():
            keywordGroups = gr.Textbox(label="Rated Groups - each of these tags will be rated", value = "Overall,RealisticArtist")
            unratedGroups = gr.Textbox(label="Unrated Groups - used as filter but will not be rated ", value = "")

        
        gr.Markdown("(Not functional yet.) Remove an unwanted tag here after image generation.  ") #add some vertical white space
        gr.Markdown(" <br/> ") 

        #Todo: Not functioning yet
        with gr.Row():
            removeTagInput = gr.Textbox(label="Name of tag to be removed")
            removeTagLeftButton = gr.Button(value = "Remove from left keyword")
            removeTagRightButton = gr.Button(value = "Remove from right keyword")

        gr.Markdown("Miscellaneous Settings ") #add some vertical white space
        gr.Markdown(" <br/> ") 

        number_of_comparisons = gr.Textbox(label="Number of Images per keyword (integer)", value = 3)
        eloScaleInput = gr.Slider(label = "Max elo change. Even ratings will occur by half this amount. Not recommended to change.", minimum = 32, maximum = 50, value = 32, )
        useNewcomerEloMultiplierInput = gr.Checkbox(label = "Increase eloScale by up to 5 for tags with few ratings.", value = True)
    
        #different_seeds = gr.Checkbox(label='Use different seed for each picture', value=False)

        return [ number_of_comparisons, keywordGroups, unratedGroups, eloScaleInput, useNewcomerEloMultiplierInput ]

    def run(self, p, number_of_comparisons, keywordGroups, unratedGroups, eloScaleInput, useNewcomerEloMultiplierInput):
        modules.processing.fix_seed(p)

        global state, eloScale, useNewcomerEloMultiplier

        groups = keywordGroups.split(",")
        unratedGroupList = unratedGroups.split(",")
        eloScale = int(eloScaleInput)
        useNewcomerEloMultiplier = useNewcomerEloMultiplierInput


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

        def populateKeywordList():
            keywords = []
            
            file_dir = os.path.dirname(os.path.realpath("__file__"))
            read_file = os.path.join(file_dir, f"scripts/SDRatings/SDRatings.txt")
            
            if os.path.exists(read_file):
                with open(read_file, 'r') as f:
                    #if a line contains all specified groups, return keyword from format keyword(group1, group2,...)
                    for line in f.read().splitlines():
                        keep = True
                        for group in groups + unratedGroupList:
                            if group not in line:
                                keep = False
                        
                        if keep:
                            keeper = line.split("(")[0]
                            keeper = keeper.strip()
                            keywords.append(keeper)
                
                    f.close()
            random.shuffle(keywords)

            return keywords

        #Don't know why I was having issues with Number instead of textbox, my workaround
        number_of_comparisons = int(number_of_comparisons)

        #global keyword1, keyword2, keywordList
        global keywordList, oldInputs
        
        #determine if settings have changed, record these settings to compare next time
        if oldInputs[0] == keywordGroups and oldInputs[1] == unratedGroups:
            newSettings = False
        else:
            newSettings = True

        oldInputs = [keywordGroups, unratedGroups]

        #Todo: Change logic and move into the for loop so that you can loop around if batch count is high
        #Todo: do something here if you ever use batch size
        if len(keywordList) < 2 * p.n_iter or newSettings:
            keywordList = populateKeywordList()
            if len(keywordList) < 2:               
                #keyword1 = "defaulta"
                #keyword2 = "defaultb"
                raise gr.Error("There aren't two or more keywords with the group")

        original_prompt = p.prompt[0] if type(p.prompt) == list else p.prompt

        #Todo: figure out what to do with batch size if anything
        wildcard_prompts = ["".join(replace_wildcard(chunk) for chunk in original_prompt.split("__")) for _ in range(p.n_iter * number_of_comparisons)]

        all_prompts = []

        for i in range(len(wildcard_prompts)):
            all_prompts.append(wildcard_prompts[i].replace("keyword", keywordList[2 * (i // number_of_comparisons)]))
            all_prompts.append(wildcard_prompts[i].replace("keyword", keywordList[2 * (i // number_of_comparisons) + 1]))
        
        #Todo: do something if data is not valid

        p.n_iter = math.ceil(len(all_prompts) / p.batch_size)
        p.do_not_save_grid = True

        print("all_prompts length : " + str(len(all_prompts)))
        p.prompt = all_prompts
        p.seed = [p.seed + (i / 2) for i in range(len(all_prompts))]
        p.prompt_for_display = original_prompt
        processed = process_images(p)
        print("Length of Processed:.images " + str(len(processed.images)))

        global contestList

        # grid = images.image_grid(processed.images, p.batch_size, rows=1 << ((len(prompt_matrix_parts) - 1) // 2))
        # grid = images.draw_prompt_matrix(grid, p.width, p.height, prompt_matrix_parts)
        #print ("Length of all_prompts" + strlen(all_prompts))
        for i in all_prompts:
            print(i)
      
        for i in range(len(all_prompts) // 2 // number_of_comparisons):
            #the strange seeming +i are due to ineserting near the start every loop and making one longer
            grid = images.image_grid(processed.images[i * 6 + i : i * 6 + 6 + i ], p.batch_size, rows=number_of_comparisons)
            
            processed.images.insert(i, grid) #Package all info into to be voted on later
            
            #To do: put in "(vs keywordList[1]) or something like that in the info text?
            processed.infotexts.insert(i, processed.infotexts[6*i + i ]) 
            contestList.append(Contest(keywordList[0:2], groups, grid))
            keywordList.pop(0)
            keywordList.pop(0)

        processed.index_of_first_image = i

        #Todo get labels to behave -- or maybe not, so ratings are unbiased. Could add check box
        #grid = images.draw_prompt_matrix(grid, p.width, p.height, all_prompts)
        #grid = images.draw_prompt_matrix(grid, p.width, p.height, all_prompts[0:2])

        #Todo add checks to make sure an image propertly displayed

        state = "ready" #allows rating buttons to work

        if opts.grid_save:
            images.save_image(processed.images[0], p.outpath_grids, "prompt_matrix", extension=opts.grid_format, prompt=original_prompt, seed=processed.seed, grid=True, p=p)

        return processed
